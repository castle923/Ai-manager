import { useEffect, useRef, useState, type RefObject } from "react";
import { AudioDownload } from "./DesktopHost";
import {
  AlertTriangle,
  ArrowRight,
  Download,
  GitCompareArrows,
  Play,
  ShieldCheck,
  Square,
} from "lucide-react";

type Run = {
  id: string;
  status: string;
  error?: string;
  model: { name: string; revision: string; preparation_id: string };
  metrics?: {
    loading_seconds?: number;
    inference_seconds?: number;
    total_seconds?: number;
    peak_gpu_allocated_bytes?: number;
  };
  audio_url?: string | null;
  input_sha256: string;
  output?: {
    sha256: string;
    duration_seconds: number;
    sample_rate: number;
    bytes: number;
  } | null;
};
type Evaluation = {
  preference: string;
  notes: string;
  recorded_at: string;
  source: string;
};
type Comparison = {
  id: string;
  status: string;
  created_at: string;
  finished_at?: string;
  input_sha256: string;
  text: string;
  parameters: {
    seed?: number;
    language?: string;
    speaker?: string;
    max_new_tokens?: number;
    sampling?: Record<string, boolean | number>;
  };
  run_ids: string[];
  runs: Run[];
  evaluation: Evaluation | null;
  conditions: {
    cold_loading: boolean;
    execution_order: string[];
    sample_count_per_model: number;
    cache_reuse: boolean;
  };
};
type Model = {
  id: string;
  name: string;
  revision: string;
  preparation_state: string;
  blockers: string[];
};
type Status = {
  supported_models: Model[];
  defaults: { max_text_length: number; timeout_seconds: number };
  comparisons: Comparison[];
  queued_runs: number;
  queue_capacity: number;
  active_run_id: string | null;
  owner_available: boolean;
};
const labels: Record<string, string> = {
  queued: "순서 대기",
  preparing: "입력·모델 확인 중",
  loading: "모델 로딩 중",
  running: "새 음성 생성 중",
  validating: "출력 검증 중",
  cancelling: "취소 처리 중",
  completed: "두 모델 생성·검증 완료",
  partial: "부분 완료 · 한쪽 결과 확인 필요",
  failed: "비교 실패",
  cancelled: "비교 취소",
  interrupted: "비교 중단",
  succeeded: "생성·파일 검증 완료",
  ready: "파일 준비 완료",
  idle: "준비 필요",
  downloading: "파일 전송 중",
  verifying: "무결성 검증 중",
  blocked: "준비 차단",
};
const reasons: Record<string, string> = {
  model_not_ready: "모델 파일 준비가 필요합니다.",
  runtime_not_ready: "별도 실행 환경 점검이 필요합니다.",
  model_integrity_failed: "모델 무결성을 확인하지 못했습니다.",
  queue_full:
    "두 실행을 위한 대기 공간이 부족합니다. 진행 중인 작업이 끝난 뒤 요청하세요.",
  text_required: "새 한국어 문장을 입력하세요.",
  text_too_long: "입력 글자 수 한도를 초과했습니다.",
  invalid_request: "요청 내용을 확인해 주세요.",
  comparison_not_completed:
    "두 모델이 모두 성공한 비교에만 평가를 기록할 수 있습니다.",
  inference_out_of_memory: "GPU 메모리가 부족해 실행하지 못했습니다.",
  inference_timeout: "실행 제한 시간을 초과했습니다.",
  generation_limit_reached:
    "생성 길이 한도에 도달했습니다. 문장을 줄여 새 비교를 요청하세요.",
  cancelled: "사용자가 취소했습니다.",
  process_interrupted: "앱 또는 실행 프로세스가 중단됐습니다.",
};
const label = (value: string) => labels[value] || value;
const reason = (value: string) =>
  reasons[value] || `확인이 필요한 상태입니다. (${value})`;
const seconds = (value?: number) =>
  value == null ? "미수집" : `${value.toFixed(2)}초`;
const terminal = (value: string) =>
  ["completed", "partial", "failed", "cancelled", "interrupted"].includes(
    value,
  );
const preferenceLabels: Record<string, string> = {
  A: "A 선호",
  B: "B 선호",
  tie: "차이 없음",
  undecided: "판단 보류",
};

export function ComparisonPanel({
  csrf,
  onPrepare,
}: {
  csrf: RefObject<string>;
  onPrepare: () => void;
}) {
  const audioPlayers = useRef(new Map<string, HTMLAudioElement>());
  const [data, setData] = useState<Status | null>(null);
  const [text, setText] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [pair, setPair] = useState<string[]>([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [stale, setStale] = useState(false);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const controller = new AbortController();
    async function poll() {
      try {
        const response = await fetch("/api/comparisons/status", {
          signal: controller.signal,
        });
        const body = await response.json();
        if (!response.ok) throw Error(reason(body.error || "request_failed"));
        if (active) {
          setData(body);
          setStale(false);
        }
      } catch (e) {
        if (active && (e as Error).name !== "AbortError") setStale(true);
      } finally {
        if (active) timer = setTimeout(poll, 1500);
      }
    }
    void poll();
    return () => {
      active = false;
      controller.abort();
      clearTimeout(timer);
    };
  }, [refresh]);
  const models = data?.supported_models || [];
  const ids =
    pair.length === 2 ? pair : models.slice(0, 2).map((model) => model.id);
  const chosen = ids.map((id) => models.find((model) => model.id === id));
  const comparisons = data?.comparisons || [];
  const comparison =
    comparisons.find((item) => item.id === selected) || comparisons[0];
  const length = Array.from(text).length;
  const max = data?.defaults.max_text_length || 300;
  const ready =
    chosen.length === 2 &&
    chosen.every(
      (model) => model?.preparation_state === "ready" && !model.blockers.length,
    );
  const hasCapacity = data
    ? data.queued_runs + 2 <= data.queue_capacity
    : false;
  const canCreate =
    Boolean(data && csrf.current) &&
    ready &&
    data?.owner_available === true &&
    hasCapacity &&
    !pending &&
    !stale &&
    Boolean(text.trim()) &&
    length <= max;
  async function mutate(path: string, body: object) {
    if (pending || stale || !csrf.current) return;
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
      if (!response.ok) throw Error(reason(result.error || "request_failed"));
      setSelected(result.comparison.id);
      setData((old) =>
        old
          ? {
              ...old,
              comparisons: [
                result.comparison,
                ...old.comparisons.filter(
                  (item) => item.id !== result.comparison.id,
                ),
              ],
            }
          : old,
      );
      setRefresh((value) => value + 1);
    } catch (e) {
      setError(
        e instanceof TypeError
          ? "로컬 앱에 연결하지 못했습니다. 상태를 다시 확인하세요."
          : (e as Error).message,
      );
    } finally {
      setPending(false);
    }
  }
  return (
    <div className="comparison-page">
      <section className="panel comparison-intro">
        <div className="tts-model-icon">
          <GitCompareArrows size={25} />
        </div>
        <div>
          <span className="eyebrow">FRESH A/B COMPARISON</span>
          <h2>같은 문장, 두 모델의 새 목소리</h2>
          <p>
            모델을 하나씩 새로 로딩하고 동일한 한국어 입력과 seed로 실행합니다.
          </p>
        </div>
        <span className="badge blue">모델당 1회 측정</span>
      </section>
      {(error || stale) && (
        <div className="banner danger" role="alert">
          <AlertTriangle size={20} />
          <span>
            {error || "비교 상태를 불러오지 못했습니다."}
            {stale ? " 마지막 응답은 현재 상태로 확정할 수 없습니다." : ""}
          </span>
          <button
            onClick={() => {
              setError("");
              setRefresh((v) => v + 1);
            }}
          >
            상태 다시 확인
          </button>
        </div>
      )}
      <div className="comparison-setup">
        <section className="panel comparison-input">
          <div className="tts-card-heading">
            <h2>새 비교 만들기</h2>
            <span className="badge neutral">GPU 순차 실행</span>
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (canCreate)
                void mutate("/api/comparisons", { text, model_ids: ids });
            }}
          >
            <fieldset className="comparison-models">
              <legend>비교 모델 · A 다음 B 순서</legend>
              {["A", "B"].map((side, index) => (
                <div key={side}>
                  <label htmlFor={`comparison-model-${side}`}>
                    모델 {side}
                  </label>
                  <select
                    id={`comparison-model-${side}`}
                    value={ids[index] || ""}
                    disabled={!data || pending}
                    onChange={(e) => {
                      const next = [...ids];
                      const other = index ? 0 : 1;
                      if (next[other] === e.target.value)
                        next[other] = next[index];
                      next[index] = e.target.value;
                      setPair(next);
                    }}
                  >
                    {models.map((model) => (
                      <option key={model.id} value={model.id}>
                        {model.name}
                      </option>
                    ))}
                  </select>
                  <small>
                    {chosen[index]
                      ? label(chosen[index]!.preparation_state)
                      : "상태 확인 중"}
                  </small>
                  {chosen[index]?.blockers.map((blocker) => (
                    <p className="comparison-blocker" key={blocker}>
                      {reason(blocker)}
                    </p>
                  ))}
                </div>
              ))}
            </fieldset>
            {data && data.owner_available !== true && (
              <p className="comparison-blocker" role="status">
                다른 앱 실행이 GPU 작업 큐를 소유합니다. 해당 앱 종료 후 이 앱을
                재시작하세요.
              </p>
            )}
            {!ready && data && (
              <div className="comparison-prepare">
                <span>
                  두 모델의 파일·환경이 모두 준비되어야 시작할 수 있습니다.
                </span>
                <button type="button" onClick={onPrepare}>
                  모델 준비 <ArrowRight size={14} />
                </button>
              </div>
            )}
            <label htmlFor="comparison-text">
              두 모델이 읽을 새 한국어 문장
            </label>
            <textarea
              id="comparison-text"
              rows={4}
              value={text}
              onChange={(e) => setText(e.target.value)}
              aria-describedby="comparison-input-help comparison-count"
              aria-invalid={length > max}
              placeholder="이번 비교를 위해 새 문장을 입력하세요."
            />
            <div className="tts-input-meta">
              <span id="comparison-input-help">
                {length > max
                  ? `${max}자 이내로 줄여 주세요.`
                  : "두 모델에 같은 입력을 전달합니다."}
              </span>
              <span
                id="comparison-count"
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
                batch <strong>1</strong>
              </span>
              <span>
                지시문 <strong>없음</strong>
              </span>
            </div>
            <button
              className="primary tts-start"
              type="submit"
              disabled={!canCreate}
            >
              <Play size={16} />
              {pending ? "요청 처리 중…" : "두 모델 새 비교 시작"}
            </button>
            {data && !hasCapacity && (
              <p className="comparison-blocker">
                대기열 공간이 부족합니다. 두 실행을 위한 공간이 생기면 시작할 수
                있습니다.
              </p>
            )}
          </form>
        </section>
        <aside className="panel comparison-guide">
          <span className="eyebrow">MEASUREMENT CONDITIONS</span>
          <h2>수치와 청취를 함께 확인하세요</h2>
          <ul>
            <li>각 요청에서 두 실행 ID와 WAV를 새로 생성합니다.</li>
            <li>
              모델을 순차로 콜드 로딩합니다. 결과 캐시를 사용하지 않습니다.
            </li>
            <li>전체 시간은 실행별 무결성 확인을 포함합니다.</li>
            <li>
              GPU 메모리는 PyTorch 최대 할당량입니다. PC 전체 메모리가 아닙니다.
            </li>
            <li>
              한 번의 측정은 통계적 우열이나 품질 순위를 증명하지 않습니다.
            </li>
          </ul>
          <div className="tts-footnote">
            <ShieldCheck size={20} />
            <p>
              파일 검증은 청취 품질 평가와 구분합니다. 선호는 두 결과를 들은
              사용자가 직접 기록합니다.
            </p>
          </div>
        </aside>
      </div>
      <section
        className="panel comparison-results"
        aria-labelledby="comparison-heading"
      >
        <div className="tts-card-heading">
          <h2 id="comparison-heading">
            {comparison ? "선택한 비교 결과" : "새 비교 결과"}
          </h2>
          {comparison && (
            <span
              className={`badge ${comparison.status === "completed" ? "green" : "amber"}`}
            >
              {label(comparison.status)}
            </span>
          )}
        </div>
        {!comparison ? (
          <div className="tts-empty">
            <GitCompareArrows size={35} />
            <h3>
              {data ? "아직 비교 기록이 없습니다" : "비교 상태를 확인하는 중…"}
            </h3>
            <p>
              같은 새 문장으로 실행한 A/B 음성과 측정값을 이곳에서 확인합니다.
            </p>
          </div>
        ) : (
          <>
            <div className="comparison-session">
              <p className="tts-run-text">{comparison.text}</p>
              <div role="status" aria-live="polite">
                {label(comparison.status)}
                {!terminal(comparison.status) && (
                  <span> · 실제 실행 종료를 기다립니다.</span>
                )}
              </div>
              {!terminal(comparison.status) && (
                <button
                  className="secondary"
                  disabled={
                    pending || stale || comparison.status === "cancelling"
                  }
                  onClick={() =>
                    void mutate(`/api/comparisons/${comparison.id}/cancel`, {})
                  }
                >
                  <Square size={14} />두 실행 취소
                </button>
              )}
            </div>
            <div className="comparison-condition-chips">
              <span>
                {comparison.conditions.cold_loading
                  ? "콜드 로딩"
                  : "로딩 조건 확인 필요"}
              </span>
              <span>실행 순서 A → B</span>
              <span>
                모델당 {comparison.conditions.sample_count_per_model}회
              </span>
              <span>
                결과 캐시{" "}
                {comparison.conditions.cache_reuse
                  ? "사용됨 · 조건 확인 필요"
                  : "사용 안 함"}
              </span>
              <span>공통 seed {comparison.parameters.seed ?? "미수집"}</span>
            </div>
            <div className="comparison-output-grid">
              {comparison.runs.map((run, index) => (
                <ComparisonOutput
                  key={run.id}
                  run={run}
                  side={index ? "B" : "A"}
                  registerAudio={(audio) => {
                    if (audio) audioPlayers.current.set(run.id, audio);
                    else audioPlayers.current.delete(run.id);
                  }}
                  onActivate={() => {
                    for (const [id, audio] of audioPlayers.current) {
                      if (id !== run.id) audio.pause();
                    }
                  }}
                />
              ))}
            </div>
            <EvaluationForm
              key={comparison.id + (comparison.evaluation?.recorded_at || "")}
              comparison={comparison}
              disabled={pending || stale}
              onSave={(body) =>
                void mutate(
                  `/api/comparisons/${comparison.id}/evaluation`,
                  body,
                )
              }
            />
            <details className="tts-evidence">
              <summary>비교 출처·공통 조건</summary>
              <dl>
                <div>
                  <dt>비교 ID</dt>
                  <dd>
                    <code>{comparison.id}</code>
                  </dd>
                </div>
                <div>
                  <dt>요청 시각</dt>
                  <dd>
                    {new Date(comparison.created_at).toLocaleString("ko-KR")}
                  </dd>
                </div>
                <div>
                  <dt>입력 SHA-256</dt>
                  <dd>
                    <code>{comparison.input_sha256}</code>
                  </dd>
                </div>
                <div>
                  <dt>실제 실행 순서</dt>
                  <dd>{comparison.conditions.execution_order.join(" → ")}</dd>
                </div>
                <div>
                  <dt>출력 토큰 한도</dt>
                  <dd>{comparison.parameters.max_new_tokens ?? "미수집"}</dd>
                </div>
                <div>
                  <dt>공통 sampling 설정</dt>
                  <dd>
                    <code>
                      {comparison.parameters.sampling
                        ? JSON.stringify(comparison.parameters.sampling)
                        : "미수집"}
                    </code>
                  </dd>
                </div>
              </dl>
            </details>
          </>
        )}
      </section>
      <section className="panel comparison-history">
        <div className="tts-card-heading">
          <h2>이 프로젝트의 비교 기록</h2>
          <span className="badge neutral">{comparisons.length}개</span>
        </div>
        <p className="tts-subtitle">
          기록 조회입니다. 이전 결과를 새 비교 입력이나 새 측정값으로 사용하지
          않습니다.
        </p>
        {comparisons.map((item) => (
          <button
            key={item.id}
            className={`comparison-history-item ${comparison?.id === item.id ? "selected" : ""}`}
            aria-pressed={comparison?.id === item.id}
            onClick={() => {
              setSelected(item.id);
              setError("");
            }}
          >
            <span>
              <strong>{item.text}</strong>
              <small>
                {new Date(item.created_at).toLocaleString("ko-KR")} · 과거 요청
                기록
              </small>
            </span>
            <span className="badge neutral">{label(item.status)}</span>
          </button>
        ))}
      </section>
    </div>
  );
}
function ComparisonOutput({
  run,
  side,
  registerAudio,
  onActivate,
}: {
  run: Run;
  side: string;
  registerAudio: (audio: HTMLAudioElement | null) => void;
  onActivate: () => void;
}) {
  const [playback, setPlayback] = useState("");
  const playable = run.status === "succeeded" && run.audio_url && run.output;
  return (
    <article className="comparison-output">
      <div className="comparison-output-heading">
        <span className="comparison-side">{side}</span>
        <div>
          <h3>{run.model.name}</h3>
          <span
            className={`badge ${run.status === "succeeded" ? "green" : "neutral"}`}
          >
            {label(run.status)}
          </span>
        </div>
      </div>
      {run.error && (
        <p className="tts-run-error" role="alert">
          {reason(run.error)}
          <small>오류 코드: {run.error}</small>
        </p>
      )}
      {playable ? (
        <div className="tts-audio">
          <audio
            ref={registerAudio}
            controls
            preload="metadata"
            src={run.audio_url!}
            aria-label={`모델 ${side}의 새 생성 음성`}
            onPlay={() => {
              onActivate();
              setPlayback("재생 중");
            }}
            onPause={() => setPlayback("일시 정지")}
            onEnded={() => setPlayback("재생 완료")}
            onError={() => setPlayback("재생 오류 · 파일 연결을 확인하세요")}
          />
          <p role="status">{playback || "재생 버튼을 눌러 직접 들어보세요."}</p>
          <div className="comparison-audio-meta">
            <span>
              {seconds(run.output!.duration_seconds)} ·{" "}
              {run.output!.sample_rate.toLocaleString()} Hz
            </span>
            <AudioDownload id={run.id} url={run.audio_url!}>
              <Download size={14} />
              {side} WAV 저장
            </AudioDownload>
          </div>
        </div>
      ) : (
        <div className="comparison-no-audio">검증된 WAV가 아직 없습니다.</div>
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
        <div>
          <dt>GPU 최대 할당</dt>
          <dd>
            {run.metrics?.peak_gpu_allocated_bytes == null
              ? "미수집"
              : `${(run.metrics.peak_gpu_allocated_bytes / 1024 ** 3).toFixed(2)} GiB`}
          </dd>
        </div>
      </dl>
      <details className="tts-evidence">
        <summary>{side} 실행 출처·해시</summary>
        <dl>
          <div>
            <dt>실행 ID</dt>
            <dd>
              <code>{run.id}</code>
            </dd>
          </div>
          <div>
            <dt>모델 revision</dt>
            <dd>
              <code>{run.model.revision}</code>
            </dd>
          </div>
          <div>
            <dt>준비 ID</dt>
            <dd>
              <code>{run.model.preparation_id || "미수집"}</code>
            </dd>
          </div>
          <div>
            <dt>입력 SHA-256</dt>
            <dd>
              <code>{run.input_sha256}</code>
            </dd>
          </div>
          <div>
            <dt>WAV SHA-256</dt>
            <dd>
              <code>{run.output?.sha256 || "검증된 출력 없음"}</code>
            </dd>
          </div>
        </dl>
      </details>
    </article>
  );
}
function EvaluationForm({
  comparison,
  disabled,
  onSave,
}: {
  comparison: Comparison;
  disabled: boolean;
  onSave: (body: { preference: string; notes: string }) => void;
}) {
  const [preference, setPreference] = useState(
    comparison.evaluation?.preference || "",
  );
  const [notes, setNotes] = useState(comparison.evaluation?.notes || "");
  const eligible =
    comparison.status === "completed" &&
    comparison.runs.length === 2 &&
    comparison.runs.every((run) => run.status === "succeeded");
  return (
    <form
      className="comparison-evaluation"
      onSubmit={(e) => {
        e.preventDefault();
        if (eligible && preference && !disabled) onSave({ preference, notes });
      }}
    >
      <h3>내 청취 평가</h3>
      <p>
        발음·자연스러움·속도를 직접 듣고 선호를 기록하세요. 자동 품질 승자를
        정하지 않습니다.
      </p>
      {!eligible && (
        <p className="comparison-blocker">
          두 모델의 생성과 파일 검증을 모두 완료한 뒤 평가할 수 있습니다.
        </p>
      )}
      <fieldset disabled={!eligible || disabled}>
        <legend>내 선호 선택</legend>
        <div className="comparison-preferences">
          {Object.entries(preferenceLabels).map(([value, title]) => (
            <label key={value}>
              <input
                type="radio"
                name="comparison-preference"
                value={value}
                checked={preference === value}
                onChange={() => setPreference(value)}
              />
              {title}
            </label>
          ))}
        </div>
        <label htmlFor="comparison-notes">청취 메모</label>
        <textarea
          id="comparison-notes"
          rows={2}
          maxLength={2000}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="직접 확인한 발음이나 자연스러움을 적으세요."
        />
        <button className="secondary" disabled={!preference} type="submit">
          내 평가 저장
        </button>
      </fieldset>
      {comparison.evaluation && (
        <p className="comparison-evaluation-saved" role="status">
          사용자 기록: {preferenceLabels[comparison.evaluation.preference]} ·{" "}
          {new Date(comparison.evaluation.recorded_at).toLocaleString("ko-KR")}
        </p>
      )}
    </form>
  );
}
