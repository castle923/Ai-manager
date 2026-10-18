import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  AudioLines,
  CircleHelp,
  FileText,
  RefreshCw,
  Square,
} from "lucide-react";
import { TaskDownload } from "./DesktopHost";

type Adapter = {
  id: string;
  name: string;
  task_type: string;
  configuration: string;
  implementation_available: boolean;
  runtime: { status: string; blockers?: string[] };
  blocker?: string;
  execution_blockers?: string[];
  execution_advisories?: string[];
  memory_requirements?: {
    gpu_total_min_bytes: number;
    gpu_free_min_bytes: number;
    ram_available_min_bytes: number;
    disk_free_min_bytes: number;
  };
  revision?: string;
  license?: string;
};
type RegisteredModel = {
  id: string;
  row_version: number;
  metadata: { name: string };
  artifact: { adapter_id: string; revision: string };
  archived: boolean;
  configuration_attention: boolean;
};
type InputInfo = { bytes: number; sha256: string; duration_seconds?: number };
type Output = {
  id: string;
  filename: string;
  mime: string;
  bytes: number;
  sha256: string;
};
type TaskRun = {
  id: string;
  adapter_id: string;
  task_type: string;
  status: string;
  started_at?: string;
  input: InputInfo;
  parameters: Record<string, unknown>;
  model: { name: string; revision: string };
  metrics: Record<string, unknown>;
  error: string | null;
  outputs: Output[];
  registry_binding?: { id: string; generation?: string };
};
type Snapshot = {
  catalog: Adapter[];
  runs: TaskRun[];
  active_run_id: string | null;
};
type AudioInput = InputInfo & { name: string; base64: string };
const terminal = new Set(["succeeded", "failed", "cancelled", "interrupted"]);
const taskLabels: Record<string, string> = {
  stt: "음성 → 텍스트",
  image: "이미지 생성",
  llm: "텍스트 생성",
  tracking: "영상 점 추적",
};
const states: Record<string, string> = {
  queued: "실행 대기",
  preparing: "입력·모델 확인 중",
  loading: "모델 로딩 중",
  running: "추론 중",
  validating: "출력 검증 중",
  succeeded: "실행 완료",
  failed: "실행 실패",
  cancelled: "취소됨",
  cancelling: "취소 처리 중",
  interrupted: "실행 중단",
};
const messages: Record<string, string> = {
  runtime_memory_feasibility_unconfirmed:
    "메모리 요구량과 실행 가능성을 확인해야 합니다.",
  model_components_incomplete: "필수 모델 구성요소가 완성되지 않았습니다.",
  checkpoint_loader_unconfirmed: "체크포인트 로더와 구성을 확인해야 합니다.",
  adapter_manifest_unavailable:
    "고정 모델 구성과 무결성 목록이 준비되지 않았습니다.",
  adapter_runtime_not_ready: "이 모델의 별도 추론 환경이 준비되지 않았습니다.",
  configuration_required:
    "모델 관리에서 보관 위치와 구성 상태를 먼저 확인하세요.",
  artifact_files_changed:
    "등록 모델 파일이 변경되었거나 접근할 수 없습니다. 보관 위치와 무결성을 확인하세요.",
  registered_artifact_mismatch: "등록한 모델과 실행 구성이 일치하지 않습니다.",
  model_integrity_failed: "모델 파일의 무결성 검사에 실패했습니다.",
  model_archived: "보관한 모델은 실행할 수 없습니다.",
  input_audio_invalid:
    "16 kHz · 모노 · PCM 16-bit WAV를 선택하세요. 길이는 30초 이하, 크기는 960,128 bytes 이하이며 무음 파일은 지원하지 않습니다.",
  input_changed: "입력 파일의 무결성이 달라 실행을 중단했습니다.",
  stale_edit:
    "모델 등록 정보가 변경되었습니다. 목록을 새로고침하고 다시 선택하세요.",
  operation_running: "다른 앱이 실행 큐를 사용하고 있습니다.",
  queue_full:
    "실행 대기열이 가득 찼습니다. 진행 중인 작업이 끝난 뒤 요청하세요.",
  inference_timeout: "제한 시간 안에 모델 실행을 마치지 못했습니다.",
  inference_out_of_memory: "GPU 메모리가 부족해 실행을 마치지 못했습니다.",
  generation_limit_reached:
    "출력 길이 제한에 도달했습니다. 더 짧은 입력을 준비하세요.",
  worker_crashed: "실행 프로세스가 정상 완료되지 않았습니다.",
  inference_failed: "모델 실행에 실패했습니다. 입력과 실행 환경을 확인하세요.",
  runtime_version_mismatch:
    "현재 모델의 고정 라이브러리 버전과 실행 환경이 일치하지 않습니다.",
  memory_budget_unavailable:
    "현재 PC의 GPU·메모리·저장 공간 여유가 실행 조건에 부족합니다. 이 작업은 시작하지 않습니다.",
  resource_limit_reached:
    "실행 중 관찰한 자원이 허용 범위를 벗어나 작업을 중단했습니다.",
  resource_guard_unavailable:
    "이 작업자의 자원을 안전하게 확인할 수 없어 실행을 중단했습니다.",
  output_invalid: "출력의 형식 또는 무결성 검증에 실패했습니다.",
  output_not_ready: "검증된 출력이 아직 준비되지 않았습니다.",
  process_interrupted:
    "앱 종료 등으로 실행이 중단되었습니다. 이 기록은 성공 결과가 아닙니다.",
  adapter_unsupported: "이 모델은 현재 실행을 지원하지 않습니다.",
  cancelled: "사용자 요청으로 실행을 취소했습니다.",
};
function explain(code: string) {
  return messages[code] || `요청을 완료하지 못했습니다. 오류 코드: ${code}`;
}
function errorText(error: unknown) {
  return error instanceof Error
    ? error.message
    : "연결 상태를 확인한 뒤 다시 시도하세요.";
}
function bytes(value: number) {
  return `${value.toLocaleString("ko-KR")} bytes`;
}
function time(value?: string) {
  if (!value) return "시각 미확인";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "시각 미확인"
    : date.toLocaleString("ko-KR");
}
async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { cache: "no-store", ...init });
  const value = await response.json();
  if (!response.ok)
    throw new Error(
      explain(
        typeof value.error === "string"
          ? value.error
          : `HTTP ${response.status}`,
      ),
    );
  return value;
}
async function inspectAudio(file: File): Promise<AudioInput> {
  if (file.size <= 44 || file.size > 960128)
    throw new Error(messages.input_audio_invalid);
  const buffer = await file.arrayBuffer();
  const view = new DataView(buffer);
  const raw = new Uint8Array(buffer);
  const text = (offset: number, count: number) =>
    String.fromCharCode(...raw.subarray(offset, offset + count));
  if (
    text(0, 4) !== "RIFF" ||
    text(8, 4) !== "WAVE" ||
    view.getUint32(4, true) + 8 !== buffer.byteLength
  )
    throw new Error(messages.input_audio_invalid);
  let validFormat = false,
    dataOffset = 0,
    dataBytes = 0;
  for (let offset = 12; offset + 8 <= buffer.byteLength; ) {
    const size = view.getUint32(offset + 4, true),
      start = offset + 8;
    if (start + size > buffer.byteLength)
      throw new Error(messages.input_audio_invalid);
    if (text(offset, 4) === "fmt " && size >= 16) {
      validFormat =
        view.getUint16(start, true) === 1 &&
        view.getUint16(start + 2, true) === 1 &&
        view.getUint32(start + 4, true) === 16000 &&
        view.getUint16(start + 14, true) === 16;
    }
    if (text(offset, 4) === "data") {
      dataOffset = start;
      dataBytes = size;
    }
    offset = start + size + (size % 2);
  }
  if (
    !validFormat ||
    !dataBytes ||
    dataBytes % 2 ||
    dataBytes > 960000 ||
    !raw
      .subarray(dataOffset, dataOffset + dataBytes)
      .some((value) => value !== 0)
  )
    throw new Error(messages.input_audio_invalid);
  const hash = new Uint8Array(await crypto.subtle.digest("SHA-256", buffer));
  let binary = "";
  for (let offset = 0; offset < raw.length; offset += 8192)
    binary += String.fromCharCode(...raw.subarray(offset, offset + 8192));
  return {
    name: file.name,
    bytes: file.size,
    duration_seconds: dataBytes / 32000,
    sha256: Array.from(hash, (value) =>
      value.toString(16).padStart(2, "0"),
    ).join(""),
    base64: btoa(binary),
  };
}

export function TaskPanel({
  csrf,
  initialRunId,
}: {
  csrf: string;
  initialRunId?: string;
}) {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [models, setModels] = useState<RegisteredModel[]>([]);
  const [modelId, setModelId] = useState("");
  const [selectedId, setSelectedId] = useState(initialRunId || "");
  const [audio, setAudio] = useState<AudioInput | null>(null);
  const [prompt, setPrompt] = useState("");
  const [pointsText, setPointsText] = useState('[{"x":0.5,"y":0.5}]');
  const [checking, setChecking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const [notice, setNotice] = useState("");
  const [reload, setReload] = useState(0);
  const [transcript, setTranscript] = useState<{
    runId: string;
    text: string;
    error: string;
  } | null>(null);
  const audioSequence = useRef(0);
  const alive = useRef(true);
  const selectedHeading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      audioSequence.current += 1;
    };
  }, []);
  useEffect(() => {
    if (initialRunId) setSelectedId(initialRunId);
  }, [initialRunId]);
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    const update = async () => {
      let delay = 8000;
      try {
        const [next, registry] = await Promise.all([
          request<Snapshot>("/api/tasks/status", { signal: controller.signal }),
          request<{ models: RegisteredModel[] }>("/api/registry", {
            signal: controller.signal,
          }),
        ]);
        if (controller.signal.aborted) return;
        setSnapshot(next);
        setModels(registry.models);
        setLoadError("");
        if (next.runs.some((run) => !terminal.has(run.status))) delay = 2000;
      } catch (cause) {
        if (controller.signal.aborted) return;
        setLoadError(errorText(cause));
      }
      if (!controller.signal.aborted) timer = setTimeout(update, delay);
    };
    void update();
    return () => {
      controller.abort();
      if (timer) clearTimeout(timer);
    };
  }, [reload]);
  const availableModels = models.filter(
    (model) =>
      !model.archived &&
      snapshot?.catalog.some(
        (adapter) =>
          adapter.id === model.artifact.adapter_id &&
          adapter.implementation_available,
      ),
  );
  const model = availableModels.find((item) => item.id === modelId);
  const adapter = snapshot?.catalog.find(
    (item) => item.id === model?.artifact.adapter_id,
  );
  const run = snapshot?.runs.find((item) => item.id === selectedId);
  const canStart = Boolean(
    model &&
      adapter?.runtime.status === "ready" &&
      !adapter.execution_blockers?.length &&
      !model.configuration_attention &&
      (adapter?.task_type === "stt" || adapter?.task_type === "tracking"
        ? audio
        : prompt.trim()) &&
      csrf &&
      !busy &&
      !checking &&
      !loadError,
  );
  const textOutputId = run?.outputs.find((output) =>
    ["transcript", "response", "tracks", "image_metadata"].includes(output.id),
  )?.id;
  const transcriptRunId =
    run?.status === "succeeded" && Boolean(textOutputId) ? run.id : "";
  useEffect(() => {
    if (!transcriptRunId) return;
    const controller = new AbortController();
    request<{ text: string }>(
      `/api/tasks/runs/${encodeURIComponent(transcriptRunId)}/outputs/${textOutputId}`,
      { signal: controller.signal },
    )
      .then((value) => {
        if (!controller.signal.aborted)
          setTranscript({
            runId: transcriptRunId,
            text:
              typeof value.text === "string"
                ? value.text
                : JSON.stringify(value, null, 2),
            error: "",
          });
      })
      .catch((cause) => {
        if (!controller.signal.aborted)
          setTranscript({
            runId: transcriptRunId,
            text: "",
            error: errorText(cause),
          });
      });
    return () => controller.abort();
  }, [transcriptRunId, textOutputId, reload]);
  async function chooseAudio(file?: File) {
    const sequence = ++audioSequence.current;
    setAudio(null);
    setError("");
    setNotice("");
    if (!file) {
      setChecking(false);
      return;
    }
    setChecking(true);
    try {
      let result: AudioInput;
      if (adapter?.task_type === "tracking") {
        if (file.size > 5000000 || file.size < 12)
          throw new Error("MP4는 5 MB 이하여야 합니다.");
        const buffer = await file.arrayBuffer();
        const raw = new Uint8Array(buffer);
        if (String.fromCharCode(...raw.slice(4, 8)) !== "ftyp")
          throw new Error("정상 MP4 원본을 선택하세요.");
        let binary = "";
        for (let i = 0; i < raw.length; i += 8192)
          binary += String.fromCharCode(...raw.slice(i, i + 8192));
        const hash = new Uint8Array(
          await crypto.subtle.digest("SHA-256", buffer),
        );
        result = {
          name: file.name,
          bytes: file.size,
          sha256: Array.from(hash, (v) => v.toString(16).padStart(2, "0")).join(
            "",
          ),
          base64: btoa(binary),
        };
      } else result = await inspectAudio(file);
      if (alive.current && sequence === audioSequence.current) setAudio(result);
    } catch (cause) {
      if (alive.current && sequence === audioSequence.current)
        setError(errorText(cause));
    } finally {
      if (alive.current && sequence === audioSequence.current)
        setChecking(false);
    }
  }
  async function start(event: FormEvent) {
    event.preventDefault();
    if (!canStart || !model || !adapter) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await request<{ run: TaskRun }>(
        `/api/registry/${encodeURIComponent(model.id)}/tasks`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-AiManager-CSRF": csrf,
          },
          body: JSON.stringify({
            row_version: model.row_version,
            input:
              adapter.task_type === "stt"
                ? { audio_base64: audio!.base64 }
                : adapter.task_type === "tracking"
                  ? {
                      video_base64: audio!.base64,
                      points: JSON.parse(pointsText),
                    }
                  : adapter.task_type === "image"
                    ? { prompt }
                    : { text: prompt },
          }),
        },
      );
      if (!alive.current) return;
      setSelectedId(result.run.id);
      setSnapshot((previous) =>
        previous
          ? {
              ...previous,
              runs: [
                result.run,
                ...previous.runs.filter((item) => item.id !== result.run.id),
              ],
            }
          : previous,
      );
      setNotice(
        `새 ${taskLabels[adapter.task_type] || "모델"} 실행을 요청했습니다. 입력·모델 무결성 확인 후 시작합니다.`,
      );
      setReload((value) => value + 1);
      selectedHeading.current?.focus();
    } catch (cause) {
      if (alive.current) setError(errorText(cause));
    } finally {
      if (alive.current) setBusy(false);
    }
  }
  async function cancel() {
    if (!run || terminal.has(run.status) || busy || !csrf) return;
    setBusy(true);
    setError("");
    try {
      await request(`/api/tasks/runs/${encodeURIComponent(run.id)}/cancel`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-AiManager-CSRF": csrf,
        },
        body: "{}",
      });
      if (alive.current) {
        setNotice("취소를 요청했습니다. 실행 상태에서 종료 여부를 확인하세요.");
        setReload((value) => value + 1);
      }
    } catch (cause) {
      if (alive.current) setError(errorText(cause));
    } finally {
      if (alive.current) setBusy(false);
    }
  }
  function selectRun(id: string) {
    setSelectedId(id);
    setNotice("");
    selectedHeading.current?.focus();
  }
  return (
    <section className="task-panel registry-panel" aria-label="모델 작업 실행">
      <div className="section-title">
        <div>
          <h2>모델 작업 실행</h2>
          <p className="muted">
            등록한 모델의 지원 범위와 준비 상태를 확인하고, 새 입력으로
            실행합니다.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setReload((value) => value + 1)}
          disabled={busy}
        >
          <RefreshCw size={16} aria-hidden="true" /> 상태 새로고침
        </button>
      </div>
      {loadError ? (
        <p className="error" role="alert">
          상태를 갱신하지 못했습니다. {loadError} 이전 표시가 남아 있을 수
          있습니다.
        </p>
      ) : null}
      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}
      <p className="sr-only" role="status">
        {checking ? "입력 파일 검사 중" : notice}
      </p>
      {notice ? <p className="registry-notice">{notice}</p> : null}
      {!snapshot ? (
        <div className="empty" role="status">
          <AudioLines size={30} aria-hidden="true" />
          <h3>
            {loadError
              ? "상태를 불러오지 못했습니다"
              : "작업 상태를 불러오는 중입니다"}
          </h3>
          <p>지원 모델·실행 환경·등록 목록을 함께 확인합니다.</p>
        </div>
      ) : (
        <>
          <div className="task-catalog" aria-label="종류별 지원 상태">
            {snapshot.catalog.map((item) => (
              <article className="task-catalog-card registry-run" key={item.id}>
                <strong>{item.name}</strong>
                <p>{taskLabels[item.task_type] || item.task_type}</p>
                <span className="badge">
                  {item.execution_blockers?.length &&
                  item.implementation_available
                    ? "현재 로컬 실행 차단"
                    : item.implementation_available
                      ? item.runtime.status === "ready"
                        ? "실행 환경 준비 확인"
                        : "구현됨 · 환경 준비 필요"
                      : "실행 미지원"}
                </span>
                {item.execution_blockers?.length &&
                item.implementation_available ? (
                  <p>{item.execution_blockers.map(explain).join(" ")}</p>
                ) : !item.implementation_available ? (
                  <p>
                    {item.blocker
                      ? explain(item.blocker)
                      : "실행 어댑터가 아직 구현되지 않았습니다."}
                  </p>
                ) : item.runtime.status !== "ready" ? (
                  <p>
                    {(item.runtime.blockers?.length
                      ? item.runtime.blockers
                      : ["adapter_runtime_not_ready"]
                    )
                      .map(explain)
                      .join(" ")}
                  </p>
                ) : (
                  <p className="caption">
                    환경 준비는 실제 실행 성공을 뜻하지 않습니다. 실행별 결과를
                    확인하세요.
                  </p>
                )}
                {item.execution_advisories?.length ? (
                  <p className="caption">
                    참고: {item.execution_advisories.map(explain).join(" ")}{" "}
                    실행 시 실제 자원 조건으로 판단합니다.
                  </p>
                ) : null}
                {item.memory_requirements ? (
                  <p className="caption">
                    로컬 자원 사전 조건: GPU 전체{" "}
                    {item.memory_requirements.gpu_total_min_bytes / 1024 ** 3}{" "}
                    GiB 이상·여유{" "}
                    {item.memory_requirements.gpu_free_min_bytes / 1024 ** 3}{" "}
                    GiB 이상, RAM 여유{" "}
                    {item.memory_requirements.ram_available_min_bytes /
                      1024 ** 3}{" "}
                    GiB 이상, 저장 공간 여유{" "}
                    {item.memory_requirements.disk_free_min_bytes / 1024 ** 3}{" "}
                    GiB 이상입니다. 현재 여유량을 측정한 표시가 아니며, 모델
                    로딩 전에 다시 확인합니다.
                  </p>
                ) : null}
              </article>
            ))}
          </div>
          <p className="caption">
            이 앱은 현재 PC에서 실행합니다. 파일 발견·구성 확인·환경 준비와 실제
            실행 성공은 서로 다릅니다. 자원은 실행 시작 시 다시 확인하며, 별도
            원격 실험의 성공을 현재 PC의 실행 검증으로 표시하지 않습니다.
          </p>
          <div className="task-layout registry-layout">
            <div className="registry-detail">
              <h2>새 모델 실행</h2>
              <p className="caption">
                유형별 구현·모델 구성·별도 환경을 구분합니다. 준비되지 않은
                모델은 실행을 차단합니다.
              </p>
              <form onSubmit={start}>
                <label htmlFor="task-model">
                  등록 모델
                  <select
                    id="task-model"
                    value={modelId}
                    onChange={(event) => {
                      setModelId(event.target.value);
                      setError("");
                      setAudio(null);
                    }}
                    disabled={busy}
                    aria-describedby="task-model-help"
                  >
                    <option value="">모델을 선택하세요</option>
                    {availableModels.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.metadata.name}
                        {item.configuration_attention
                          ? " · 구성 확인 필요"
                          : ""}
                      </option>
                    ))}
                  </select>
                </label>
                <p id="task-model-help" className="caption">
                  {availableModels.length
                    ? "보관되지 않은 등록 모델 중 고정 어댑터 구성을 표시합니다."
                    : "실행할 모델이 등록되지 않았습니다. 모델 관리에서 지원 모델과 로컬 보관 위치를 등록하세요."}
                </p>
                {model && adapter ? (
                  <div className="task-status-strip registry-run">
                    <strong>{model.metadata.name}</strong>
                    <p>
                      {model.configuration_attention
                        ? "등록 구성 확인 필요"
                        : "등록 구성 확인됨"}{" "}
                      ·{" "}
                      {adapter.runtime.status === "ready"
                        ? "별도 추론 환경 준비 확인"
                        : "별도 추론 환경 미준비"}
                    </p>
                    <p className="caption">
                      선택 모델 revision:{" "}
                      <code className="registry-path">
                        {model.artifact.revision}
                      </code>
                    </p>
                    {adapter.license ? (
                      <p className="caption">라이선스: {adapter.license}</p>
                    ) : null}
                  </div>
                ) : null}
                {adapter?.task_type === "llm" ||
                adapter?.task_type === "image" ? (
                  <label htmlFor="task-prompt">
                    이번 새{" "}
                    {adapter.task_type === "image"
                      ? "이미지 프롬프트"
                      : "텍스트 입력"}
                    <textarea
                      id="task-prompt"
                      rows={5}
                      maxLength={2000}
                      value={prompt}
                      onChange={(e) => setPrompt(e.target.value)}
                    />
                    <small>
                      입력은 새 실행에 보존합니다. LLM은 템플릿 포함 최대 256
                      토큰·출력 64 토큰으로 제한합니다.
                    </small>
                  </label>
                ) : (
                  <>
                    <label htmlFor="task-audio">
                      {adapter?.task_type === "tracking"
                        ? "이번 실행의 MP4 원본"
                        : "이번 실행의 WAV 원본"}
                      <input
                        id="task-audio"
                        type="file"
                        accept={
                          adapter?.task_type === "tracking"
                            ? ".mp4,video/mp4"
                            : ".wav,audio/wav,audio/x-wav"
                        }
                        disabled={busy || checking}
                        onChange={(event) =>
                          void chooseAudio(event.currentTarget.files?.[0])
                        }
                        aria-describedby="task-audio-help"
                      />
                      <small id="task-audio-help">
                        {adapter?.task_type === "tracking"
                          ? "MP4 최대 5 MB · 최대 32 프레임·20초·8점. 좌표는 첫 프레임의 정규화 x/y(0~1), 추적은 256×256으로 변환합니다."
                          : "16 kHz · 모노 · PCM 16-bit · 30초 이하 · 최대 960,128 bytes."}
                        파일을 자동 변환하지 않습니다. 이번 작업에 지정한 원본
                        또는 새 녹음을 선택하세요.
                      </small>
                    </label>
                    {checking ? (
                      <p role="status">
                        WAV 구조와 SHA-256을 확인하고 있습니다.
                      </p>
                    ) : audio ? (
                      <dl className="registry-facts">
                        <dt>선택 파일</dt>
                        <dd>{audio.name}</dd>
                        <dt>길이·크기</dt>
                        <dd>
                          {audio.duration_seconds?.toFixed(3) ?? "미확인"}초 ·{" "}
                          {bytes(audio.bytes)}
                        </dd>
                        <dt>입력 SHA-256</dt>
                        <dd>
                          <code>{audio.sha256}</code>
                        </dd>
                      </dl>
                    ) : (
                      <p className="caption">
                        선택한 파일이 없습니다. 서버에서도 입력과 모델 무결성을
                        다시 확인합니다.
                      </p>
                    )}
                    {adapter?.task_type === "tracking" ? (
                      <label htmlFor="task-points">
                        첫 프레임 추적점 JSON (1~8점)
                        <textarea
                          id="task-points"
                          rows={3}
                          value={pointsText}
                          onChange={(e) => setPointsText(e.target.value)}
                        />
                        <small>
                          예: [{"{"}"x":0.5,"y":0.5{"}"}]는 화면 중앙입니다.
                          원본 좌표와 출력 좌표 변환을 결과 JSON에 기록합니다.
                        </small>
                      </label>
                    ) : null}
                  </>
                )}
                <div className="registry-actions">
                  <button
                    className="primary"
                    type="submit"
                    disabled={!canStart}
                  >
                    <AudioLines size={16} aria-hidden="true" />
                    {busy ? "요청 처리 중…" : "새 모델 실행"}
                  </button>
                </div>
                {!csrf ? (
                  <p className="caption">
                    보안 연결을 확인 중입니다. 연결 완료 후 실행할 수 있습니다.
                  </p>
                ) : null}
                <details>
                  <summary>실행 조건과 지원 한계</summary>
                  <p>
                    {adapter?.task_type === "stt"
                      ? "한국어 고정 · transcribe · seed 0 · 샘플링 없음 · 최대 출력 토큰 256. 구간별 타임스탬프는 지원하지 않습니다."
                      : adapter?.task_type === "tracking"
                        ? "첫 프레임의 1~8개 정규화 좌표를 추적합니다. 최대 32프레임을 256×256으로 변환하며 원본 시간과 좌표 변환을 기록합니다."
                        : adapter?.task_type === "llm"
                          ? "seed 0 · 샘플링 없음 · 입력 템플릿 포함 최대 256토큰 · 출력 최대 64토큰. 배치 예산은 실제 메모리 상한을 보장하지 않습니다."
                          : "이 앱의 로컬 이미지는 512×512 · 4단계 · seed 0의 제한된 시험 조건입니다. 라이선스와 실행 전 자원 조건을 확인합니다. 별도 원격 고품질 실험은 이 화면에 연결되지 않으며 현재 PC의 성공 근거가 아닙니다."}
                    품질과 일반 정확도는 별도 확인이 필요합니다.
                  </p>
                  <p>
                    입력과 결과는 앱의 실행별 로컬 기록에 보존합니다. 이
                    화면에서 다른 프로젝트 결과를 자동 검색하거나 입력으로
                    가져오지 않습니다.
                  </p>
                </details>
              </form>
            </div>
            <section
              className="registry-detail task-result"
              aria-labelledby="task-selected-title"
            >
              <h2 id="task-selected-title" ref={selectedHeading} tabIndex={-1}>
                실행 상세
              </h2>
              {!run ? (
                <div className="empty">
                  <FileText size={30} aria-hidden="true" />
                  <h3>
                    {selectedId
                      ? "실행 기록을 찾지 못했습니다"
                      : "확인할 실행을 선택하세요"}
                  </h3>
                  <p>
                    {selectedId
                      ? "기록이 현재 앱에 있는지 확인하고 새로고침하세요."
                      : "새 실행을 요청하거나 아래 이력에서 작업 결과를 선택하세요."}
                  </p>
                </div>
              ) : (
                <>
                  <p role="status" aria-live="polite">
                    <span className="badge">
                      {states[run.status] || "상태 미확인"}
                    </span>{" "}
                    {run.model.name}
                  </p>
                  <p className="caption">
                    {time(run.started_at)} · 이력 조회입니다. 이전 결과를 새
                    실행 성공으로 계산하지 않습니다.
                  </p>
                  {run.error ? (
                    <p
                      className={
                        run.status === "cancelled" ? "registry-notice" : "error"
                      }
                      role={run.status === "cancelled" ? "status" : "alert"}
                    >
                      {explain(run.error)}
                    </p>
                  ) : null}
                  {!terminal.has(run.status) ? (
                    <div className="registry-actions">
                      <button
                        type="button"
                        onClick={() => void cancel()}
                        disabled={busy || !csrf || run.status === "cancelling"}
                      >
                        <Square size={14} aria-hidden="true" />
                        {run.status === "cancelling"
                          ? "취소 처리 중…"
                          : "이 실행 취소"}
                      </button>
                    </div>
                  ) : null}
                  {run.status === "succeeded" ? (
                    <div className="task-transcript">
                      <h3>실행 결과</h3>
                      {run.outputs
                        .filter((output) => output.mime === "image/png")
                        .map((output) => (
                          <img
                            key={output.id}
                            style={{ maxWidth: "100%", height: "auto" }}
                            src={`/api/tasks/runs/${run.id}/outputs/${output.id}`}
                            alt={
                              output.id === "preview"
                                ? "이번 영상 추적 결과의 첫·중간·마지막 프레임"
                                : "이번 프롬프트로 생성한 이미지"
                            }
                          />
                        ))}
                      {transcript?.runId === run.id ? (
                        transcript.error ? (
                          <p role="alert" className="error">
                            {transcript.error}
                          </p>
                        ) : (
                          <p
                            style={{
                              whiteSpace: "pre-wrap",
                              overflowWrap: "anywhere",
                            }}
                          >
                            {transcript.text}
                          </p>
                        )
                      ) : (
                        <p role="status">검증된 결과를 불러오는 중입니다.</p>
                      )}
                      <p className="caption">
                        타입별 결과·좌표·생성 조건은 검증된 JSON과 원본 입력을
                        대조해 확인하세요.
                      </p>
                    </div>
                  ) : null}
                  <h3>이번 실행 기록</h3>
                  <dl className="registry-facts">
                    <dt>실행 ID</dt>
                    <dd>
                      <code>{run.id}</code>
                    </dd>
                    <dt>모델 revision</dt>
                    <dd>
                      <code>{run.model.revision}</code>
                    </dd>
                    <dt>입력</dt>
                    <dd>
                      {run.input.duration_seconds?.toFixed(3) ?? "해당 없음"}초
                      · {bytes(run.input.bytes)}
                    </dd>
                    <dt>입력 SHA-256</dt>
                    <dd>
                      <code>{run.input.sha256}</code>
                    </dd>
                    <dt>등록 연결</dt>
                    <dd>{run.registry_binding?.id || "연결 기록 없음"}</dd>
                  </dl>
                  <details>
                    <summary>실행 조건·측정값</summary>
                    <h3>고정 실행 조건</h3>
                    <pre className="registry-path">
                      {JSON.stringify(run.parameters, null, 2)}
                    </pre>
                    <h3>측정값 (실행 기록 기준)</h3>
                    {Object.keys(run.metrics || {}).length ? (
                      <pre className="registry-path">
                        {JSON.stringify(run.metrics, null, 2)}
                      </pre>
                    ) : (
                      <p>아직 측정값이 없습니다. 예측치를 표시하지 않습니다.</p>
                    )}
                  </details>
                  {run.outputs.length ? (
                    <section aria-label="검증된 출력 파일">
                      <h3>출력 파일</h3>
                      {run.outputs.map((output) => (
                        <div className="registry-run" key={output.id}>
                          <strong>{output.filename}</strong>
                          <p>
                            {output.mime} · {bytes(output.bytes)}
                          </p>
                          <p className="caption registry-path">
                            SHA-256: <code>{output.sha256}</code>
                          </p>
                          <div className="registry-actions">
                            <TaskDownload
                              id={run.id}
                              outputId={output.id}
                              url={`/api/tasks/runs/${encodeURIComponent(run.id)}/outputs/${encodeURIComponent(output.id)}`}
                            >
                              {output.filename + " 저장"}
                            </TaskDownload>
                          </div>
                        </div>
                      ))}
                    </section>
                  ) : null}
                </>
              )}
            </section>
          </div>
          <section
            className="registry-list"
            aria-labelledby="task-history-title"
          >
            <div className="section-title">
              <h2 id="task-history-title">작업 실행 이력</h2>
              <span className="muted">
                {snapshot.runs.length.toLocaleString("ko-KR")}건
              </span>
            </div>
            <p className="caption">
              <CircleHelp size={14} aria-hidden="true" /> 과거 실행은 해당
              실행의 기록입니다. 현재 모델·환경의 성공 여부는 새 실행으로
              확인합니다.
            </p>
            {snapshot.runs.length ? (
              <div className="table-wrap">
                <table>
                  <caption className="sr-only">
                    새 입력별 작업 실행 상태와 상세 선택
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col">실행 모델·시각</th>
                      <th scope="col">상태</th>
                      <th scope="col">입력 길이</th>
                      <th scope="col">결과 확인</th>
                    </tr>
                  </thead>
                  <tbody>
                    {snapshot.runs.map((item) => (
                      <tr
                        key={item.id}
                        className={
                          selectedId === item.id
                            ? "registry-selected"
                            : undefined
                        }
                      >
                        <th scope="row">
                          {item.model.name}
                          <small>{time(item.started_at)}</small>
                          <small>{item.id}</small>
                        </th>
                        <td>{states[item.status] || "상태 미확인"}</td>
                        <td>
                          {item.input.duration_seconds?.toFixed(3) ??
                            "해당 없음"}
                          초
                        </td>
                        <td>
                          <button
                            type="button"
                            onClick={() => selectRun(item.id)}
                            aria-label={`${item.model.name}, ${time(item.started_at)} 실행 상세 보기`}
                            aria-pressed={selectedId === item.id}
                          >
                            상세 보기
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="empty">
                <h3>실행 이력이 없습니다</h3>
                <p>
                  모델 준비 후 새 입력으로 지원 모델을 실행하면 여기에
                  기록됩니다.
                </p>
              </div>
            )}
          </section>
        </>
      )}
    </section>
  );
}
