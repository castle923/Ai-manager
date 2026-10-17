import { useEffect, useState, type RefObject } from "react";
import {
  AlertTriangle,
  Check,
  Clock,
  Download,
  HardDrive,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";

type PreparationFile = {
  path: string;
  size: number;
  sha256?: string;
  downloaded_bytes?: number;
  origin?: string;
  official_supplement?: {
    url: string;
    reason: string;
    observed_drive_bytes: number;
  };
  status?: string;
};
type PreparationData = {
  supported_model: { id: string; name: string; revision: string };
  plan: {
    status: string;
    files: PreparationFile[];
    total_bytes: number;
    required_bytes: number;
    free_bytes: number | null;
    blockers: string[];
    account?: string;
    source?: string;
  };
  preparation: {
    id?: string | null;
    status: string;
    downloaded_bytes: number;
    total_bytes: number;
    current_file?: string | null;
    files_verified: number;
    error?: string | null;
    configuration: string;
    integrity: string;
    runtime: string;
    execution: string;
    files?: PreparationFile[];
    environment?: Record<string, unknown>;
  };
};
const stateLabels: Record<string, string> = {
  idle: "아직 준비하지 않음",
  downloading: "파일 전송 중",
  verifying: "파일 무결성 검증 중",
  ready: "모델 파일 준비 완료",
  failed: "준비 실패",
  cancelled: "준비 취소",
  interrupted: "이전 준비 중단",
  available: "준비 요청 가능",
  blocked: "준비 차단",
  complete: "필수 구성 충족",
  missing: "필수 구성 부족",
  matched: "공식 SHA-256 일치",
  mismatched: "해시 불일치",
  unverified: "미확인",
  not_run: "실행하지 않음",
  pending: "전송 대기",
  verified: "해시 확인 완료",
  downloaded: "전송 완료",
  partial: "일부 전송",
};
const reasons: Record<string, string> = {
  preparation_io_failed:
    "준비 중 파일 처리나 상태 저장을 완료하지 못했습니다. 실패 기록과 부분 파일은 보존됩니다. 저장소의 여유 공간·쓰기 권한과 다른 프로그램의 파일 사용 여부를 확인한 뒤 새 실행으로 재시도하세요. 정확한 원인은 추가 확인이 필요합니다.",
  preparation_failed:
    "준비 작업을 완료하지 못했습니다. 실패 기록과 부분 파일을 보존하고 원인을 확인한 뒤 새 실행으로 재시도하세요.",
  local_asset_changed:
    "준비 후 로컬 파일이 변경됐거나 기록과 일치하지 않습니다. 무결성 완료 판정을 해제했습니다. 새 실행으로 다시 준비하고 검증하세요.",
  outside_allowlist:
    "선정 출처가 승인된 폴더 범위에 속하지 않아 다운로드를 차단했습니다. 허용한 원본 폴더를 확인하세요.",
  partial_source_listing:
    "원본 폴더의 전체 목록을 확인하지 못해 준비를 중단했습니다. 연결 상태와 읽기 권한을 확인한 뒤 다시 수집하세요.",
  ambiguous_component:
    "같은 필수 파일의 출처 후보가 여러 개여서 다운로드를 차단했습니다. 원본 구성을 확인하세요.",
  unsafe_path:
    "안전한 저장 경로로 확인할 수 없는 파일이 있어 준비를 차단했습니다. 원본 파일 이름과 구성을 확인하세요.",
  runtime_record_invalid:
    "저장된 환경 점검 기록을 읽거나 검증하지 못했습니다. 환경을 다시 점검하세요.",
  runtime_probe_failed:
    "환경 점검 프로세스를 완료하지 못했습니다. 별도 실행 환경의 설치 상태를 확인한 뒤 다시 점검하세요.",
  runtime_import_failed:
    "환경의 필수 패키지를 불러오지 못했습니다. 의존성 설치와 호환성을 확인한 뒤 환경을 다시 점검하세요.",
  authentication_required:
    "선정 출처 계정의 인증이 필요합니다. 계정 및 수집에서 연결을 확인하세요.",
  authentication_refresh_failed:
    "다운로드에 필요한 인증을 갱신하지 못했습니다. 계정 및 수집에서 인증 갱신을 확인하고 필요하면 다시 로그인하세요.",
  network_retry_exhausted:
    "네트워크 요청을 여러 번 시도했지만 완료하지 못했습니다. 연결을 확인한 뒤 새 실행으로 재시도하세요.",
  retry_exhausted:
    "원본 조회의 재시도 한도를 초과했습니다. 연결과 읽기 권한을 확인한 뒤 다시 시도하세요.",
  invalid_json:
    "원본 서비스의 응답 형식을 읽지 못했습니다. 연결을 확인한 뒤 다시 시도하세요.",
  invalid_response:
    "원본 서비스에서 예상한 응답을 받지 못했습니다. 다시 시도하세요.",
  invalid_file_id:
    "원본 파일 식별 정보를 확인하지 못했습니다. 허용된 목록을 다시 수집하세요.",
  invalid_folder_id:
    "원본 폴더 식별 정보를 확인하지 못했습니다. 허용된 목록을 다시 수집하세요.",
  download_network_interrupted:
    "파일 전송 중 네트워크가 끊겼습니다. 부분 파일은 보존됩니다. 연결을 확인한 뒤 새 실행으로 재시도하세요.",
  download_auth_retry:
    "파일 전송의 인증 재시도 한도를 초과했습니다. 계정 인증을 확인한 뒤 새 실행으로 재시도하세요.",
  download_retryable:
    "원본 서비스의 요청 제한이나 일시 오류로 전송 재시도 한도를 초과했습니다. 잠시 후 새 실행으로 재시도하세요.",
  download_invalid_range:
    "원본 서비스의 응답 범위나 전송 크기가 요청과 일치하지 않아 다운로드를 차단했습니다. 부분 파일은 보존되며 준비 완료로 표시하지 않습니다.",
  forbidden:
    "이 로컬 앱의 요청을 인증하지 못했습니다. 화면을 새로고침한 뒤 다시 시도하세요.",
  json_required:
    "요청 형식이 올바르지 않습니다. 화면을 새로고침한 뒤 다시 시도하세요.",
  invalid_request:
    "준비 요청의 내용이 올바르지 않습니다. 선정 모델과 계정을 확인하세요.",
  not_found: "요청한 준비 정보를 찾지 못했습니다. 화면을 다시 불러오세요.",
  model_not_found: "허용된 인벤토리에서 선정 모델을 찾지 못했습니다.",
  ambiguous_model: "선정 모델 출처가 여러 개여서 결정할 수 없습니다.",
  missing_component: "필수 구성요소가 부족합니다.",
  source_changed: "수집 후 원본 정보가 변경되었습니다. 다시 수집하세요.",
  size_mismatch: "공식 파일 크기와 다운로드한 크기가 다릅니다.",
  runtime_not_checked: "환경을 아직 점검하지 않았습니다.",
  runtime_dependency_missing: "런타임 의존성이 부족합니다.",
  cuda_unavailable: "CUDA 장치를 사용할 수 없습니다.",
  unsupported_runtime: "현재 런타임은 지원 조건을 충족하지 못했습니다.",
  insufficient_disk: "여유 디스크 공간이 부족합니다.",
  disk_space_insufficient: "여유 디스크 공간이 부족합니다.",
  not_connected: "선정 출처 계정의 로그인이 필요합니다.",
  source_missing: "허용한 수집 목록에서 선정 모델을 찾지 못했습니다.",
  missing_required_files: "필수 모델 파일이 누락됐습니다.",
  configuration_missing: "필수 구성요소가 부족합니다.",
  hash_mismatch:
    "공식 해시와 파일 내용이 다릅니다. 해당 파일은 준비 완료로 표시되지 않습니다.",
  integrity_mismatch: "공식 해시와 파일 내용이 다릅니다.",
  runtime_unsupported:
    "현재 환경은 지원하는 런타임 조건을 충족하지 못했습니다.",
  unsupported_model: "현재 이 모델의 준비 어댑터는 지원하지 않습니다.",
  cancelled: "사용자가 준비 작업을 취소했습니다.",
  process_interrupted: "이전 프로세스에서 준비 작업이 중단됐습니다.",
  network_error: "네트워크 연결을 확인한 뒤 다시 시도하세요.",
  operation_running: "다른 작업이 진행 중입니다.",
  request_failed: "준비 상태를 불러오지 못했습니다.",
};
const label = (value: string) => stateLabels[value] || value;
const reason = (value: string) => {
  if (reasons[value]) return reasons[value];
  const http = /^(?:download_http_|http_retry_exhausted_|http_)(\d{3})$/.exec(
    value,
  );
  if (http) {
    const status = Number(http[1]);
    const message =
      status === 401
        ? "원본 서비스의 인증이 만료됐습니다. 계정 인증을 확인하세요."
        : status === 403
          ? "원본 파일 읽기 권한이 거부됐습니다. 승인된 계정과 읽기 권한을 확인하세요."
          : status === 404
            ? "원본 파일을 찾지 못했습니다. 허용된 목록을 다시 수집하세요."
            : status === 429
              ? "원본 서비스의 요청 제한으로 전송을 완료하지 못했습니다. 잠시 후 다시 시도하세요."
              : status >= 500
                ? "원본 서비스의 일시 오류로 요청을 완료하지 못했습니다. 잠시 후 다시 시도하세요."
                : "원본 서비스가 요청을 받아들이지 않았습니다. 연결과 원본 상태를 확인하세요.";
    return `${message} (HTTP ${status})`;
  }
  return `준비 작업에서 확인이 필요한 오류가 발생했습니다. 기록을 보존하고 원인을 확인한 뒤 다시 시도하세요. (${value})`;
};
const failureMessage = (error: unknown) =>
  error instanceof TypeError
    ? "로컬 앱의 응답을 확인하지 못했습니다. 앱 실행 상태와 연결을 확인한 뒤 다시 불러오세요."
    : error instanceof SyntaxError
      ? "로컬 앱의 응답 형식을 읽지 못했습니다. 화면을 다시 불러오세요."
      : (error as Error).message;
const size = (value: number | null | undefined) =>
  value == null
    ? "미확인"
    : new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 2 }).format(
        value /
          (value >= 1024 ** 3 ? 1024 ** 3 : value >= 1024 ** 2 ? 1024 ** 2 : 1),
      ) + (value >= 1024 ** 3 ? " GiB" : value >= 1024 ** 2 ? " MiB" : " B");
const environmentLabels: Record<string, string> = {
  python: "Python",
  python_version: "Python 버전",
  torch: "PyTorch",
  torch_version: "PyTorch 버전",
  cuda_available: "CUDA 사용 가능",
  cuda_version: "CUDA 버전",
  device: "장치",
  gpu: "GPU",
  qwen_tts: "Qwen TTS",
  qwen_tts_version: "Qwen TTS 버전",
  status: "환경 판정",
  platform: "운영체제",
  packages: "설치 패키지",
  checks: "점검 항목",
  blockers: "환경 차단 이유",
  checked_at: "점검 시각",
  error: "환경 오류",
  sox_available: "SoX 사용 가능",
  probe_sha256: "점검 코드 SHA-256",
};
function environmentValue(value: unknown): string {
  if (value === true) return "확인됨";
  if (value === false) return "충족하지 않음";
  if (value == null) return "미확인";
  if (Array.isArray(value))
    return value.map(environmentValue).join(" · ") || "없음";
  if (typeof value === "object")
    return Object.entries(value)
      .map(
        ([key, child]) =>
          `${environmentLabels[key] || key}: ${environmentValue(child)}`,
      )
      .join(" · ");
  return value === "ready"
    ? "환경 점검 통과"
    : reasons[String(value)] || label(String(value));
}
export function PreparationPanel({
  busy,
  canCancel,
  csrf,
}: {
  busy: boolean;
  canCancel: boolean;
  csrf: RefObject<string>;
}) {
  const [modelId, setModelId] = useState("qwen3-tts-0.6b-customvoice");
  const [data, setData] = useState<PreparationData | null>(null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [stale, setStale] = useState(false);
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const controller = new AbortController();
    async function poll() {
      try {
        const response = await fetch(
          `/api/preparation?model_id=${encodeURIComponent(modelId)}`,
          {
            signal: controller.signal,
          },
        );
        const body = await response.json();
        if (!response.ok) throw Error(reason(body.error || "request_failed"));
        if (active) {
          setData(body);
          setError("");
          setStale(false);
        }
      } catch (e) {
        if (active && (e as Error).name !== "AbortError") {
          setError(failureMessage(e));
          setStale(true);
        }
      } finally {
        if (active) timer = setTimeout(poll, 1800);
      }
    }
    poll();
    return () => {
      active = false;
      controller.abort();
      clearTimeout(timer);
    };
  }, [refresh, modelId]);
  async function act(action: "prepare" | "cancel" | "runtime_check") {
    if (!csrf.current || pending) return;
    setPending(true);
    try {
      const response = await fetch("/api/action", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-AiManager-CSRF": csrf.current,
        },
        body: JSON.stringify({
          action,
          account: "B",
          ...(action === "prepare" ? { model_id: modelId } : {}),
        }),
      });
      const body = await response.json();
      if (!response.ok) throw Error(reason(body.error || "request_failed"));
      setRefresh((v) => v + 1);
    } catch (e) {
      setError(failureMessage(e));
    } finally {
      setPending(false);
    }
  }
  if (!data)
    return (
      <section
        className="panel preparation-empty"
        role={error ? "alert" : "status"}
      >
        <HardDrive size={32} />
        <h2>
          {error
            ? "준비 상태를 확인하지 못했습니다"
            : "선정 모델의 준비 조건을 확인하는 중…"}
        </h2>
        <p>{error || "필수 파일과 로컬 디스크 상태를 조회합니다."}</p>
        {error && (
          <button onClick={() => setRefresh((v) => v + 1)}>
            다시 불러오기
          </button>
        )}
      </section>
    );
  const plan = data.plan,
    run = data.preparation;
  const running = ["downloading", "verifying"].includes(run.status);
  const retry = ["failed", "cancelled", "interrupted"].includes(run.status);
  const progress =
    run.total_bytes > 0
      ? Math.min(
          100,
          Math.max(0, (run.downloaded_bytes / run.total_bytes) * 100),
        )
      : 0;
  const blockers = plan.blockers || [];
  const axes = [
    [
      "발견",
      plan.status === "available" ? "선정 출처 확인" : "출처·조건 확인 필요",
      "허용된 인벤토리에서 선정 모델을 확인합니다.",
      plan.status === "available",
    ],
    [
      "구성 충족",
      label(run.configuration),
      "필수 파일 계약을 기준으로 확인합니다.",
      run.configuration === "complete",
    ],
    [
      "파일 무결성",
      label(run.integrity),
      "다운로드한 실제 바이트와 공식 SHA-256을 비교합니다.",
      run.integrity === "matched",
    ],
    [
      "런타임 준비",
      run.runtime === "ready" ? "환경 점검 통과" : label(run.runtime),
      "별도 환경의 의존성과 장치를 점검합니다. 모델 로딩은 제외합니다.",
      run.runtime === "ready",
    ],
    [
      "실제 실행",
      "실행하지 않음",
      "실제 생성 결과는 음성 작업실·새 A/B 비교에서 확인합니다.",
      false,
    ],
  ] as const;
  return (
    <div className="preparation-page">
      <div className="panel preparation-model-selector">
        <label htmlFor="preparation-model">준비할 모델</label>
        <select
          id="preparation-model"
          value={modelId}
          disabled={busy || pending}
          onChange={(event) => {
            setModelId(event.target.value);
            setData(null);
            setError("");
          }}
        >
          <option value="qwen3-tts-0.6b-customvoice">
            Qwen3-TTS · 0.6B CustomVoice
          </option>
          <option value="qwen3-tts-1.7b-customvoice">
            Qwen3-TTS · 1.7B CustomVoice
          </option>
        </select>
      </div>
      <section className="preparation-hero panel">
        <div className="preparation-hero-top">
          <span className="eyebrow">SELECTED MODEL / FILE VERIFICATION</span>
          <span
            className={"badge " + (run.status === "ready" ? "green" : "amber")}
          >
            {label(run.status)}
          </span>
        </div>
        <h2>{data.supported_model.name}</h2>
        <p className="preparation-intro">
          한국어 음성 합성 · CustomVoice <span>선정 모델 준비 어댑터</span>
        </p>
        {plan.files.some(
          (file) =>
            file.origin === "official_model_component" ||
            file.official_supplement,
        ) && (
          <p className="preparation-source-note">
            가중치: 지정 Drive · 구성 파일{" "}
            {
              plan.files.filter(
                (file) =>
                  file.origin === "official_model_component" ||
                  file.official_supplement,
              ).length
            }
            개: 공식 고정 버전 보완 · Drive 원본 보존
          </p>
        )}
        {run.id && (
          <div className="preparation-progress">
            <div>
              <strong>{label(run.status)}</strong>
              <span>
                {size(run.downloaded_bytes)} / {size(run.total_bytes)} ·{" "}
                {progress.toFixed(1)}%
              </span>
            </div>
            <progress
              aria-label="모델 파일 전체 전송 진행률"
              max={100}
              value={progress}
            />
            <p>
              {run.current_file
                ? `현재 파일 · ${run.current_file}`
                : "현재 전송 중인 파일 없음"}
            </p>
          </div>
        )}
        <div className="preparation-actions">
          {running ? (
            <button
              onClick={() => act("cancel")}
              disabled={pending || !canCancel}
            >
              <Clock size={17} />
              {canCancel
                ? "준비 작업 취소"
                : "다른 프로세스의 준비 작업 · 여기서 취소 불가"}
            </button>
          ) : (
            <button
              className="primary"
              disabled={
                busy ||
                pending ||
                stale ||
                plan.status !== "available" ||
                run.status === "ready" ||
                !csrf.current
              }
              onClick={() => act("prepare")}
            >
              <Download size={17} />
              {pending
                ? "요청 중…"
                : retry
                  ? "새 실행으로 다시 준비"
                  : run.status === "ready"
                    ? "모델 파일 준비 완료"
                    : "이 모델만 준비하기"}
            </button>
          )}
          <button disabled={pending} onClick={() => setRefresh((v) => v + 1)}>
            <RefreshCw size={16} />
            조건 다시 확인
          </button>
          <p>
            준비 후 음성 작업실 또는 새 A/B 비교에서 실제 음성을 생성하세요.
          </p>
        </div>
        <details className="preparation-provenance">
          <summary>허용 출처 · 공식 revision · 이번 실행 기록 보기</summary>
          <dl className="preparation-source">
            <div>
              <dt>허용된 다운로드 출처</dt>
              <dd>
                계정 {plan.account || "B"} · 지정 모델 폴더 · Drive 읽기 전용
                {modelId === "qwen3-tts-1.7b-customvoice" && (
                  <small className="cell-note">
                    {plan.files
                      .filter(
                        (file) =>
                          file.origin === "official_model_component" ||
                          file.official_supplement,
                      )
                      .map((file) => file.path)
                      .join(", ")}
                    은 0바이트 Drive 파일 대신 이 화면의 공식 고정 revision에서
                    새로 받았습니다. Drive 원본은 변경하지 않습니다.
                  </small>
                )}
              </dd>
            </div>
            <div>
              <dt>공식 고정 revision</dt>
              <dd className="mono">{data.supported_model.revision}</dd>
            </div>
            <div>
              <dt>현재 준비 실행</dt>
              <dd className="mono">{run.id || "아직 생성하지 않음"}</dd>
            </div>
          </dl>
        </details>
      </section>
      {error && (
        <div className="banner danger" role="alert">
          <AlertTriangle size={19} />
          <span>
            {error}
            {stale ? " 마지막 조회 결과이며 현재 상태는 미확인입니다." : ""}
          </span>
        </div>
      )}
      {(blockers.length > 0 || run.error) && (
        <section className="banner danger preparation-blockers" role="alert">
          <AlertTriangle size={20} />
          <div>
            <strong>준비를 완료하지 못한 이유</strong>
            <ul>
              {[
                ...new Set([...blockers, ...(run.error ? [run.error] : [])]),
              ].map((item) => (
                <li key={item}>{reason(item)}</li>
              ))}
            </ul>
          </div>
        </section>
      )}
      <div className="preparation-metrics">
        <Metric
          title="필수 파일"
          value={`${plan.files.length}개`}
          note="선정 모델 계약에 포함된 파일"
        />
        <Metric
          title="총 다운로드 크기"
          value={size(plan.total_bytes)}
          note="필수 파일의 바이트 합계"
        />
        <Metric
          title="필요 디스크 공간"
          value={size(plan.required_bytes)}
          note="전송 여유 포함 · 환경 설치 별도"
        />
        <Metric
          title="현재 여유 공간"
          value={size(plan.free_bytes)}
          note="준비 저장소가 있는 디스크"
        />
      </div>
      <div className="preparation-columns">
        <section className="panel preparation-checks">
          <h3>확인 수준을 구분합니다</h3>
          <div className="verification-list">
            {axes.map(([name, state, note, checked]) => (
              <div key={name}>
                <span
                  className={"verification-icon " + (checked ? "observed" : "")}
                >
                  {checked ? <Check size={15} /> : <Clock size={15} />}
                </span>
                <div>
                  <strong>{name}</strong>
                  <small>{note}</small>
                </div>
                <span className={checked ? "observed-text" : "muted"}>
                  {state}
                </span>
              </div>
            ))}
          </div>
        </section>
        <section className="panel preparation-environment">
          <h3>환경 점검</h3>
          <button
            className="runtime-check-button"
            disabled={busy || pending || running || stale || !csrf.current}
            onClick={() => act("runtime_check")}
          >
            <RefreshCw size={15} />
            환경 다시 점검
          </button>
          <p>설치·가용성 점검과 실제 모델 실행을 구분합니다.</p>
          <dl>
            {Object.entries(run.environment || {}).length ? (
              Object.entries(run.environment || {}).map(([key, value]) => (
                <div key={key}>
                  <dt>{environmentLabels[key] || key}</dt>
                  <dd>{environmentValue(value)}</dd>
                </div>
              ))
            ) : (
              <div>
                <dt>점검 결과</dt>
                <dd>아직 확인하지 않음</dd>
              </div>
            )}
          </dl>
        </section>
      </div>
      <section className="panel preparation-files">
        <div className="preparation-files-heading">
          <div>
            <h3>필수 파일과 전송·검증</h3>
            <p>
              {run.id
                ? `${run.files_verified || 0} / ${plan.files.length}개 해시 검증`
                : "준비 요청 전 · 전송과 해시는 아직 확인하지 않았습니다."}
            </p>
          </div>
          <span className="badge neutral">공식 SHA-256 기준</span>
        </div>
        <div className="table-wrap">
          <table>
            <caption className="sr-only">
              필수 파일별 크기, 전송 상태와 공식 해시
            </caption>
            <thead>
              <tr>
                <th scope="col">필수 파일</th>
                <th scope="col">크기</th>
                <th scope="col">전송·검증 상태</th>
                <th scope="col">공식 SHA-256</th>
              </tr>
            </thead>
            <tbody>
              {plan.files.map((file) => {
                const current = run.files?.find((f) => f.path === file.path);
                return (
                  <tr key={file.path}>
                    <td>
                      <strong>{file.path}</strong>
                      {modelId === "qwen3-tts-1.7b-customvoice" && (
                        <small className="cell-note">
                          {file.origin === "official_model_component" ||
                          file.official_supplement
                            ? "공식 고정 revision 보완"
                            : file.origin === "designated_drive_component"
                              ? "지정 Drive 원본"
                              : "출처 확인 중"}
                        </small>
                      )}
                    </td>
                    <td>{size(file.size)}</td>
                    <td>
                      <span>
                        {label(
                          (current?.status === "downloading" && !running
                            ? "partial"
                            : current?.status) ||
                            (run.current_file === file.path && running
                              ? run.status
                              : "pending"),
                        )}
                      </span>
                      {current?.downloaded_bytes != null && (
                        <small className="cell-note">
                          {size(current.downloaded_bytes)} / {size(file.size)}
                        </small>
                      )}
                    </td>
                    <td>
                      <code title={file.sha256}>{file.sha256 || "미확인"}</code>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
      <div className="preparation-preservation">
        <ShieldCheck size={20} />
        <div>
          <strong>실패·취소 기록과 부분 파일은 보존합니다</strong>
          <p>
            재시도는 새 준비 실행으로 기록합니다. Drive 원본은 변경하지
            않습니다. 준비 완료는 실제 추론·음성 출력 검증을 뜻하지 않습니다.
          </p>
        </div>
      </div>
    </div>
  );
}
function Metric({
  title,
  value,
  note,
}: {
  title: string;
  value: string;
  note: string;
}) {
  return (
    <section className="panel preparation-metric">
      <span>{title}</span>
      <strong>{value}</strong>
      <p>{note}</p>
    </section>
  );
}
