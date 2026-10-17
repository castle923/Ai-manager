// View state stays in the fragment; native trust still rejects every real query.
export function appViewParams() {
  return new URLSearchParams(location.hash.replace(/^#/, ""));
}
export function replaceAppView(params: URLSearchParams) {
  const url = new URL(location.href);
  url.hash = params.toString();
  history.replaceState(null, "", url);
}

export type ViewPreferences = {
  default_section: "registry" | "history";
  history_page_size: number;
  time_display: "local" | "UTC";
  memory_unit: "MiB" | "GiB";
};
export type PreferenceRecord = {
  schema_version: number;
  revision: number;
  persisted: boolean;
  values: ViewPreferences;
};
export const defaultPreferences: ViewPreferences = {
  default_section: "registry",
  history_page_size: 25,
  time_display: "local",
  memory_unit: "GiB",
};
const messages: Record<string, string> = {
  history_invalid_query: "기록 조회 조건을 확인하세요.",
  history_snapshot_expired:
    "조회 스냅샷이 만료됐습니다. 새로 불러오면 최신 기록의 첫 페이지로 이동합니다.",
  history_snapshot_filter_mismatch:
    "조회 조건이 바뀌었습니다. 최신 기록을 새로 불러오세요.",
  history_not_found: "원본 기록을 찾을 수 없습니다.",
  preferences_invalid:
    "보기 설정 파일의 형식이나 버전을 확인해야 합니다. 기존 파일을 덮어쓰지 않았습니다.",
  preferences_unavailable:
    "보기 설정을 읽거나 저장하지 못했습니다. 기존 설정을 보존했습니다.",
  preferences_stale:
    "다른 화면에서 보기 설정이 변경됐습니다. 현재 값을 다시 불러온 뒤 저장하세요.",
  preferences_busy:
    "다른 화면이 보기 설정을 저장 중입니다. 잠시 후 현재 값을 다시 불러오세요.",
  forbidden: "요청 권한을 확인하세요.",
  performance_record_unavailable:
    "비교 원본의 형식이나 출처를 확인하지 못했습니다. 기존 기록을 보존했습니다.",
  comparison_not_found: "비교 원본 기록을 찾을 수 없습니다.",
};
export async function workspaceApi<T>(
  url: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(url, init);
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      messages[data.error] ||
        "기록을 확인하지 못했습니다. 잠시 후 다시 시도하세요.",
    );
  return data;
}
export function formatTime(
  value: string | null | undefined,
  mode: "local" | "UTC",
) {
  if (!value) return "시각 미기록";
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "시각 미기록";
  return (
    new Intl.DateTimeFormat("ko-KR", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      ...(mode === "UTC" ? { timeZone: "UTC" } : {}),
    }).format(date) + (mode === "UTC" ? " UTC" : " 현지 시각")
  );
}
export const statusLabel: Record<string, string> = {
  queued: "대기",
  staged: "큐 등록 전",
  preparing: "실행 준비",
  loading: "모델 로딩",
  running: "진행 중",
  cancelling: "취소 중",
  succeeded: "생성 완료",
  complete: "수집 완료",
  completed: "비교 완료",
  partial: "부분 완료",
  failed: "실패",
  cancelled: "취소",
  interrupted: "중단",
  ready: "준비 완료",
  blocked: "확인 필요",
  verifying: "파일 검증 중",
  downloading: "다운로드 중",
  finished: "작업 완료",
  idle: "대기",
  unknown: "확인 불가",
  not_started: "시작 전",
};
