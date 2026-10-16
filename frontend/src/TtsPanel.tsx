import { useEffect, useState, type RefObject } from "react";
import {
  AudioLines,
  Play,
  Download,
  Square,
  RefreshCw,
  ShieldCheck,
  Clock,
  AlertTriangle,
} from "lucide-react";

type Run = {
  id: string;
  status: string;
  text: string;
  started_at: string;
  finished_at?: string;
  input_sha256: string;
  error?: string | null;
  parameters: {
    language: string;
    speaker: string;
    batch_size: number;
    instruct: string | null;
  };
  model: { id: string; name: string; revision: string; preparation_id: string };
  metrics: {
    loading_seconds?: number;
    inference_seconds?: number;
    total_seconds?: number;
    peak_gpu_allocated_bytes?: number;
  };
  output: null | {
    sha256: string;
    bytes: number;
    sample_rate: number;
    channels: number;
    frames: number;
    duration_seconds: number;
    peak: number;
    rms: number;
  };
  audio_url: string | null;
};
type TtsStatus = {
  supported_model: { id: string; name: string; revision: string };
  defaults: { max_text_length: number; timeout_seconds: number };
  runs: Run[];
  active_run_id: string | null;
};
const labels: Record<string, string> = {
  queued: "순서 대기",
  preparing: "입력·모델 확인 중",
  loading: "GPU에 모델 로딩 중",
  running: "한국어 음성 생성 중",
  validating: "WAV 출력 검증 중",
  cancelling: "취소 처리 중",
  succeeded: "생성·파일 검증 완료",
  failed: "실행 실패",
  cancelled: "실행 취소",
  interrupted: "실행 중단",
};
const errors: Record<string, string> = {
  text_required: "읽을 한국어 문장을 입력하세요.",
  text_too_long: "입력 글자 수가 실행 한도를 초과했습니다.",
  invalid_request: "요청 내용을 확인한 뒤 다시 실행하세요.",
  run_not_found: "실행 기록을 찾지 못했습니다.",
  run_not_finished: "검증을 완료한 실행만 재생할 수 있습니다.",
  queue_full:
    "대기열이 가득 찼습니다. 진행 중인 실행이 끝난 뒤 다시 요청하세요.",
  runtime_not_ready:
    "별도 실행 환경이 준비되지 않았습니다. 모델 준비 화면에서 환경을 확인하세요.",
  model_not_ready: "모델 파일 준비가 필요합니다. 모델 준비 화면을 확인하세요.",
  model_integrity_failed:
    "모델 파일 무결성을 확인하지 못해 실행을 차단했습니다.",
  generation_limit_reached:
    "생성 길이 상한에 도달했습니다. 문장을 줄여 새로 실행하세요.",
  inference_timeout:
    "실행 제한 시간을 초과했습니다. 기록을 보존하고 새 실행으로 재시도하세요.",
  inference_out_of_memory:
    "GPU 메모리가 부족합니다. 다른 GPU 작업을 종료한 뒤 새 실행으로 재시도하세요.",
  inference_failed:
    "음성 생성에 실패했습니다. 이 실행의 오류 기록을 확인하세요.",
  worker_crashed:
    "실행 프로세스가 비정상 종료됐습니다. 성공 결과로 처리하지 않습니다.",
  output_invalid:
    "출력 WAV가 검증을 통과하지 못했습니다. 재생 가능한 결과로 제공하지 않습니다.",
  cancelled: "사용자가 실행을 취소했습니다. 생성 성공으로 처리하지 않습니다.",
  process_interrupted:
    "앱 또는 프로세스 종료로 실행이 중단됐습니다. 새 실행으로 다시 요청하세요.",
  forbidden: "요청 인증을 확인하지 못했습니다. 화면을 새로고침하세요.",
};
const message = (code: string) =>
  errors[code] || `실행 요청을 완료하지 못했습니다. (${code})`;
const terminal = (status: string) =>
  ["succeeded", "failed", "cancelled", "interrupted"].includes(status);
const seconds = (value: number | undefined) =>
  value == null ? "미수집" : `${value.toFixed(2)}초`;
const date = (value: string) => new Date(value).toLocaleString("ko-KR");

export function TtsPanel({ csrf }: { csrf: RefObject<string> }) {
  const [data, setData] = useState<TtsStatus | null>(null);
  const [text, setText] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [stale, setStale] = useState(false);
  const [pending, setPending] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [playback, setPlayback] = useState("");
  useEffect(() => {
    let live = true;
    let timer: ReturnType<typeof setTimeout>;
    const controller = new AbortController();
    async function poll() {
      try {
        const response = await fetch("/api/tts/status", {
          signal: controller.signal,
        });
        const body = await response.json();
        if (!response.ok) throw Error(message(body.error || "request_failed"));
        if (live) {
          setData(body);
          setStale(false);
        }
      } catch (e) {
        if (live && (e as Error).name !== "AbortError") {
          setStale(true);
        }
      } finally {
        if (live) timer = setTimeout(poll, 1500);
      }
    }
    poll();
    return () => {
      live = false;
      controller.abort();
      clearTimeout(timer);
    };
  }, [refresh]);
  const max = data?.defaults.max_text_length || 300;
  const length = Array.from(text).length;
  const invalid = !text.trim() || length > max;
  const runs = data?.runs || [];
  const run = runs.find((item) => item.id === selected) || runs[0];
  const waiting = runs.filter((item) => item.status === "queued").length;
  const canSubmit =
    Boolean(data) && !stale && !pending && !invalid && waiting < 3;
  async function mutate(path: string, body: object, create: boolean) {
    if (pending || stale || !data || !csrf.current || (create && !canSubmit))
      return;
    setPending(true);
    setError("");
    try {
      const response = await fetch(path, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-AiManager-CSRF": csrf.current,
        },
        body: JSON.stringify(body),
      });
      const result = await response.json();
      if (!response.ok) throw Error(message(result.error || "request_failed"));
      if (create) {
        setSelected(result.run.id);
        setPlayback("");
      }
      setData((previous) =>
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
      setRefresh((value) => value + 1);
    } catch (e) {
      setError(
        e instanceof TypeError
          ? "로컬 앱에 연결하지 못했습니다. 연결을 확인한 뒤 다시 요청하세요."
          : (e as Error).message,
      );
    } finally {
      setPending(false);
    }
  }
  const canPlay = run?.status === "succeeded" && run.output && run.audio_url;
  return (
    <div className="tts-page">
      <section className="panel tts-model">
        <div className="tts-model-icon">
          <AudioLines size={24} />
        </div>
        <div>
          <span className="eyebrow">LOCAL VOICE STUDIO</span>
          <h2>
            {data?.supported_model.name || "Qwen3-TTS · 0.6B CustomVoice"}
          </h2>
          <p>한국어 · Sohee · batch 1 · 지시문 없이 실행</p>
        </div>
        <span className="badge neutral">GPU 작업 1개씩</span>
      </section>
      {(error || stale) && (
        <div className="banner danger" role="alert">
          <AlertTriangle size={20} />
          <span>
            {error ||
              "실행 상태를 불러오지 못했습니다. 로컬 앱 연결을 확인하세요."}
            {stale ? " 마지막 응답은 현재 상태로 확정할 수 없습니다." : ""}
          </span>
          <button
            onClick={() => {
              setError("");
              setRefresh((value) => value + 1);
            }}
          >
            상태 다시 확인
          </button>
        </div>
      )}
      <div className="tts-columns">
        <section className="panel tts-input">
          <div className="tts-card-heading">
            <h2>새 목소리 만들기</h2>
            <span className="badge blue">새 실행</span>
          </div>
          <p className="tts-subtitle">
            지금 입력한 문장으로 새 WAV를 생성합니다.
          </p>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              if (canSubmit) void mutate("/api/tts/runs", { text }, true);
            }}
          >
            <label htmlFor="tts-text">읽을 한국어 문장</label>
            <textarea
              id="tts-text"
              value={text}
              onChange={(event) => setText(event.target.value)}
              placeholder="이번 실행에서 읽을 문장을 직접 입력하세요."
              rows={6}
              aria-describedby="tts-input-help tts-count"
              aria-invalid={length > max}
            />
            <div className="tts-input-meta">
              <span id="tts-input-help">
                {length > max
                  ? `${max}자 이내로 문장을 줄여 주세요.`
                  : "공백만 있는 입력은 실행할 수 없습니다."}
              </span>
              <span
                id="tts-count"
                className={length > max ? "tts-invalid" : ""}
              >
                {length} / {max}자
              </span>
            </div>
            <div className="tts-parameters">
              <span>
                언어 <strong>Korean</strong>
              </span>
              <span>
                목소리 <strong>Sohee</strong>
              </span>
              <span>
                한 번에 <strong>1문장</strong>
              </span>
            </div>
            <button
              className="primary tts-start"
              type="submit"
              disabled={!canSubmit}
            >
              <Play size={17} />
              {pending
                ? "요청 처리 중…"
                : data?.active_run_id
                  ? "새 실행 대기열에 추가"
                  : "새 음성 생성"}
            </button>
          </form>
          <div className="tts-footnote">
            <ShieldCheck size={17} />
            <p>
              입력·모델·출력 해시를 실행별로 기록합니다. 모델 로딩과 음성 생성
              시간은 각각 측정하며, 파일 검증과 청취 품질은 구분합니다.
            </p>
          </div>
        </section>
        <section
          className="panel tts-current"
          aria-labelledby="tts-run-heading"
        >
          <div className="tts-card-heading">
            <h2 id="tts-run-heading">선택한 실행</h2>
            <span className="badge neutral">대기 {waiting}개</span>
          </div>
          {!run ? (
            <div className="tts-empty">
              <AudioLines size={38} />
              <h3>
                {data
                  ? "아직 실행 기록이 없습니다"
                  : stale
                    ? "실행 상태를 확인하지 못했습니다"
                    : "실행 상태를 확인하는 중…"}
              </h3>
              <p>
                새 문장을 입력하고 음성을 생성하세요.
                <br />
                실제 출력이 생기면 이곳에서 재생할 수 있습니다.
              </p>
            </div>
          ) : (
            <>
              <div
                className={`tts-state ${run.status === "succeeded" ? "tts-success" : ""}`}
                role="status"
                aria-live="polite"
                aria-atomic="true"
              >
                <span>
                  {!terminal(run.status) && (
                    <RefreshCw size={18} className="spin" />
                  )}
                  {labels[run.status] || run.status}
                </span>
                <p>
                  {run.status === "loading"
                    ? "각 실행은 모델을 새로 로딩합니다. 첫 로딩에는 시간이 걸릴 수 있습니다."
                    : run.status === "running"
                      ? "진행률은 추정하지 않습니다. 음성 생성 프로세스의 실제 종료를 기다립니다."
                      : run.status === "validating"
                        ? "오디오 구조·샘플·해시를 확인한 후 재생을 제공합니다."
                        : run.status === "queued"
                          ? "앞선 GPU 작업이 끝나면 자동으로 시작합니다."
                          : run.status === "succeeded"
                            ? "WAV 파일 검증 완료 · 발음과 자연스러움은 직접 들어보세요."
                            : run.status === "cancelling"
                              ? "프로세스 종료를 확인하고 있습니다. 취소 완료까지 기다려 주세요."
                              : "새 실행의 상태와 기록입니다."}
                </p>
              </div>
              <p className="tts-run-text">{run.text}</p>
              {!terminal(run.status) && (
                <button
                  className="secondary tts-cancel"
                  disabled={pending || stale || run.status === "cancelling"}
                  onClick={() =>
                    void mutate(`/api/tts/runs/${run.id}/cancel`, {}, false)
                  }
                >
                  <Square size={14} />
                  {run.status === "cancelling"
                    ? "취소 확인 중…"
                    : "이 실행 취소"}
                </button>
              )}
              {run.error && (
                <div className="tts-run-error" role="alert">
                  {message(run.error)}
                  <small>오류 코드: {run.error}</small>
                </div>
              )}
              {canPlay && (
                <div className="tts-audio">
                  <div className="tts-card-heading">
                    <strong>이번 실행의 WAV</strong>
                    <a
                      className="secondary"
                      href={`${run.audio_url}?download=1`}
                      download
                    >
                      <Download size={15} />
                      WAV 저장
                    </a>
                  </div>
                  <audio
                    key={run.id}
                    controls
                    preload="metadata"
                    src={run.audio_url!}
                    aria-label="선택한 실행의 생성 음성"
                    onPlay={() => setPlayback(`${run.id}:재생 중`)}
                    onPause={() => setPlayback(`${run.id}:일시 정지`)}
                    onEnded={() => setPlayback(`${run.id}:재생 완료`)}
                    onError={() =>
                      setPlayback(
                        `${run.id}:재생 오류 · 파일 연결을 확인하세요`,
                      )
                    }
                  />
                  <p role="status">
                    {playback.startsWith(run.id + ":")
                      ? playback.slice(run.id.length + 1)
                      : "재생 버튼을 눌러 음성을 확인하세요."}
                  </p>
                  <span>
                    {seconds(run.output!.duration_seconds)} ·{" "}
                    {run.output!.sample_rate.toLocaleString()} Hz ·{" "}
                    {run.output!.channels}채널 ·{" "}
                    {run.output!.bytes.toLocaleString()} bytes
                  </span>
                </div>
              )}
              <dl className="tts-timings">
                <div>
                  <dt>모델 로딩</dt>
                  <dd>{seconds(run.metrics?.loading_seconds)}</dd>
                </div>
                <div>
                  <dt>음성 생성</dt>
                  <dd>{seconds(run.metrics?.inference_seconds)}</dd>
                </div>
                <div>
                  <dt>전체 실행</dt>
                  <dd>{seconds(run.metrics?.total_seconds)}</dd>
                </div>
              </dl>
              <details className="tts-evidence">
                <summary>실행 출처·검증 기록</summary>
                <dl>
                  <div>
                    <dt>실행 ID</dt>
                    <dd>
                      <code>{run.id}</code>
                    </dd>
                  </div>
                  <div>
                    <dt>시작 시각</dt>
                    <dd>{date(run.started_at)}</dd>
                  </div>
                  {run.finished_at && (
                    <div>
                      <dt>종료 시각</dt>
                      <dd>{date(run.finished_at)}</dd>
                    </div>
                  )}
                  <div>
                    <dt>모델 revision</dt>
                    <dd>
                      <code>{run.model.revision}</code>
                    </dd>
                  </div>
                  <div>
                    <dt>준비 실행 ID</dt>
                    <dd>
                      <code>{run.model.preparation_id || "확인 중"}</code>
                    </dd>
                  </div>
                  <div>
                    <dt>입력 SHA-256</dt>
                    <dd>
                      <code>{run.input_sha256}</code>
                    </dd>
                  </div>
                  <div>
                    <dt>출력 SHA-256</dt>
                    <dd>
                      <code>{run.output?.sha256 || "검증된 출력 없음"}</code>
                    </dd>
                  </div>
                  <div>
                    <dt>GPU 최대 할당 메모리</dt>
                    <dd>
                      {run.metrics?.peak_gpu_allocated_bytes == null
                        ? "미수집"
                        : `${(run.metrics.peak_gpu_allocated_bytes / 1024 ** 3).toFixed(2)} GiB`}
                    </dd>
                  </div>
                </dl>
              </details>
            </>
          )}
        </section>
      </div>
      <section className="panel tts-history">
        <div className="tts-card-heading">
          <div>
            <h2>실행 기록</h2>
            <p className="tts-subtitle">
              기록을 선택해 해당 실행의 상태와 결과를 확인합니다. 이전 실행은 새
              생성의 근거로 사용하지 않습니다.
            </p>
          </div>
          <Clock size={20} />
        </div>
        {runs.length ? (
          <ul>
            {runs.map((item) => (
              <li key={item.id}>
                <button
                  aria-pressed={run?.id === item.id}
                  onClick={() => {
                    setSelected(item.id);
                    setPlayback("");
                  }}
                >
                  <span
                    className={`badge ${item.status === "succeeded" ? "green" : ["failed", "interrupted"].includes(item.status) ? "amber" : "neutral"}`}
                  >
                    {labels[item.status] || item.status}
                  </span>
                  <span className="tts-history-text">
                    {item.text}
                    <small>
                      {date(item.started_at)} · {item.id.slice(0, 12)}
                    </small>
                  </span>
                  <span className="tts-history-time">
                    {seconds(item.metrics?.total_seconds)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="tts-subtitle">
            이번 프로젝트의 실행 기록이 여기에 표시됩니다.
          </p>
        )}
      </section>
      <p className="tts-scope-note">
        선정한 0.6B 모델의 로컬 실행 작업실입니다. 결과는 로컬 실행별 디렉터리에
        저장됩니다.
      </p>
    </div>
  );
}
