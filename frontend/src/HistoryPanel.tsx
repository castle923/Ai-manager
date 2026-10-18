import { useEffect, useRef, useState } from "react";
import { ArrowRight, History, RefreshCw, Search } from "lucide-react";
import { PerformanceChart } from "./PerformanceChart";
import {
  appViewParams,
  replaceAppView,
  formatTime,
  statusLabel,
  workspaceApi,
  type ViewPreferences,
} from "./workspace";
type HistoryItem = {
  key: string;
  kind: string;
  id: string;
  label: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  sort_at: string | null;
  time_basis: string;
  scope: string;
  read_error: boolean;
  has_error: boolean;
  source_id_available?: boolean;
  details: Record<string, unknown>;
};
type HistoryResult = {
  items: HistoryItem[];
  total: number;
  snapshot: string;
  captured_at: string;
  issues: string[];
  offset: number;
  limit: number;
  has_more: boolean;
};
const kinds: Record<string, string> = {
  model_run: "모델 유형별 실행",
  scan: "Drive 수집",
  preparation: "모델 파일 준비",
  run: "음성 실행",
  comparison: "A/B 비교",
  runtime: "현재 런타임 준비 상태",
  runtime_check: "현재 환경 점검",
  task: "앱 작업",
};
const detailLabels: Record<string, string> = {
  account: "계정",
  files_count: "관찰 파일 수",
  folders_count: "관찰 폴더 수",
  excluded_count: "제외 수",
  model_id: "실행 어댑터",
  input_sha256: "입력 SHA-256",
  comparison_id: "부모 비교 ID",
  run_ids: "하위 실행 ID",
  files_verified: "확인된 구성 파일 수",
  total_bytes: "예상 bytes",
  downloaded_bytes: "준비된 bytes",
  action: "작업 종류",
  cuda_available: "CUDA 확인",
};
function initialQuery() {
  const q = appViewParams();
  return {
    q: q.get("h_q") || "",
    kind: q.get("h_kind") || "",
    status: q.get("h_status") || "",
  };
}
export function HistoryPanel({
  preferences,
  onSource,
}: {
  preferences: ViewPreferences;
  onSource: (kind: string, id: string) => void;
}) {
  const [query, setQuery] = useState(initialQuery),
    [draft, setDraft] = useState(initialQuery),
    [offset, setOffset] = useState(() =>
      Math.max(0, Number(appViewParams().get("h_offset")) || 0),
    ),
    [data, setData] = useState<HistoryResult | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [reload, setReload] = useState(0),
    [selected, setSelected] = useState<HistoryItem | null>(null),
    [detailError, setDetailError] = useState("");
  const snapshot = useRef<string | null>(null),
    sequence = useRef(0),
    detailSequence = useRef(0),
    heading = useRef<HTMLHeadingElement>(null),
    previousPageSize = useRef(preferences.history_page_size);
  useEffect(() => {
    if (previousPageSize.current !== preferences.history_page_size) {
      previousPageSize.current = preferences.history_page_size;
      snapshot.current = null;
      setOffset(0);
    }
  }, [preferences.history_page_size]);
  useEffect(() => {
    const request = ++sequence.current;
    const controller = new AbortController();
    setBusy(true);
    setError("");
    const params = new URLSearchParams({
      ...query,
      offset: String(offset),
      limit: String(preferences.history_page_size),
    });
    if (snapshot.current) params.set("snapshot", snapshot.current);
    workspaceApi<HistoryResult>("/api/history?" + params, {
      signal: controller.signal,
    })
      .then((r) => {
        if (sequence.current === request) {
          setData(r);
          snapshot.current = r.snapshot;
        }
      })
      .catch((e) => {
        if (sequence.current === request && e.name !== "AbortError")
          setError(e.message);
      })
      .finally(() => {
        if (sequence.current === request) setBusy(false);
      });
    return () => {
      controller.abort();
    };
  }, [query, offset, preferences.history_page_size, reload]);

  useEffect(() => {
    const view = appViewParams();
    Object.entries(query).forEach(([key, value]) => {
      if (value) view.set("h_" + key, value);
      else view.delete("h_" + key);
    });
    if (offset) view.set("h_offset", String(offset));
    else view.delete("h_offset");
    replaceAppView(view);
  }, [query, offset]);
  async function detail(kind: string, id: string) {
    const request = ++detailSequence.current;
    setDetailError("");
    try {
      const r = await workspaceApi<{ item: HistoryItem }>(
        "/api/history/" + kind + "/" + id,
      );
      if (request === detailSequence.current) {
        setSelected(r.item);
        const view = appViewParams();
        view.set("h_selected", r.item.key);
        replaceAppView(view);
        setTimeout(() => heading.current?.focus(), 0);
      }
    } catch (e) {
      if (request === detailSequence.current)
        setDetailError((e as Error).message);
    }
  }
  useEffect(() => {
    const chosen = appViewParams().get("h_selected");
    if (chosen) {
      const split = chosen.indexOf(":");
      const kind = chosen.slice(0, split),
        id = chosen.slice(split + 1);
      if (
        split > 0 &&
        kinds[kind] &&
        /^(?:[a-f0-9]{32}|runtime(?:-[a-f0-9]{16})?)$/.test(id)
      )
        void detail(kind, id);
    }
    return () => {
      detailSequence.current++;
    };
  }, []);
  function refresh() {
    snapshot.current = null;
    setOffset(0);
    setReload((n) => n + 1);
  }
  function apply() {
    snapshot.current = null;
    setOffset(0);
    setQuery({ ...draft });
  }
  const clear = () => {
    const empty = { q: "", kind: "", status: "" };
    setDraft(empty);
    snapshot.current = null;
    setOffset(0);
    setQuery(empty);
  };
  return (
    <div className="workspace-panels">
      <section className="panel history-panel" aria-busy={busy}>
        <div className="tts-card-heading">
          <h2>
            <History size={20} /> 통합 작업 기록
          </h2>
          <button onClick={refresh} disabled={busy}>
            <RefreshCw size={16} /> 최신 기록 새로 불러오기
          </button>
        </div>
        <p className="muted">
          원본 기록을 읽기 전용으로 모아 봅니다. 완료 이력 조회는 새 실행·새
          인증·현재 구성의 검증을 뜻하지 않습니다.
        </p>
        <form
          className="history-filters"
          onSubmit={(e) => {
            e.preventDefault();
            apply();
          }}
        >
          <label>
            기록 검색
            <div className="history-search">
              <Search size={16} />
              <input
                value={draft.q}
                onChange={(e) => setDraft({ ...draft, q: e.target.value })}
                maxLength={300}
                placeholder="종류·원본 ID·어댑터"
              />
            </div>
          </label>
          <label>
            기록 종류
            <select
              value={draft.kind}
              onChange={(e) => setDraft({ ...draft, kind: e.target.value })}
            >
              <option value="">전체 종류</option>
              {Object.entries(kinds).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            기록 상태
            <select
              value={draft.status}
              onChange={(e) => setDraft({ ...draft, status: e.target.value })}
            >
              <option value="">전체 상태</option>
              {Object.entries(statusLabel).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <button className="primary" disabled={busy}>
            조건 적용
          </button>
          <button type="button" onClick={clear}>
            조건 초기화
          </button>
        </form>
        {error && (
          <div className="banner danger" role="alert">
            <span>{error}</span>
            <button onClick={refresh} disabled={busy}>
              최신 첫 페이지 다시 조회
            </button>
          </div>
        )}
        {data && (
          <>
            <div className="history-snapshot">
              <p>
                <strong>{data.total.toLocaleString()}개 기록</strong> · 조회
                시각 {formatTime(data.captured_at, preferences.time_display)}
              </p>
              <small>
                시작 시각 내림차순, 같은 시각은 종류·ID 순서입니다. 시작 시각이
                없으면 명시된 완료 시각을 사용하고, 시각 미기록은 마지막에
                둡니다. 페이지 이동 중 기록은 고정됩니다.
              </small>
            </div>
            {data.issues.length > 0 && (
              <div className="banner" role="status">
                일부 원본 기록을 읽지 못했습니다. 확인 가능한 기록은 계속
                표시합니다. 실패한 원본을 수정·복구하지 않았습니다.
              </div>
            )}
            {data.items.length === 0 ? (
              <div className="tts-empty">
                <History size={28} />
                <h3>
                  {query.q || query.kind || query.status
                    ? "조건에 맞는 기록이 없습니다"
                    : "저장된 작업 기록이 없습니다"}
                </h3>
                <p>
                  {query.q || query.kind || query.status
                    ? "조건을 초기화하거나 최신 기록을 조회하세요."
                    : "새 수집·모델 준비·실행이 원본 ID와 함께 이곳에 나타납니다. 현재 런타임 상태는 과거 작업 성공과 구분합니다."}
                </p>
                <button onClick={clear}>조건 초기화</button>
              </div>
            ) : (
              <div className="table-wrap">
                <table className="history-table">
                  <caption>
                    고정 조회 스냅샷의 기록 목록 · 비교 부모와 개별 실행은 별도
                    기록이며 횟수·평균으로 합산하지 않습니다.
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col">종류·원본 ID</th>
                      <th scope="col">상태</th>
                      <th scope="col">기록 시각</th>
                      <th scope="col">원본 확인</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.items.map((item) => (
                      <tr key={item.key}>
                        <th scope="row">
                          <span>{item.label}</span>
                          <code>
                            {item.source_id_available === false
                              ? "원본 ID 형식 확인 필요"
                              : item.id}
                          </code>
                          <small>
                            {item.scope === "current_state"
                              ? "현재 상태 기록"
                              : "저장된 이력"}
                          </small>
                        </th>
                        <td>
                          <span
                            className={
                              "badge " +
                              (item.read_error || item.has_error ? "amber" : "")
                            }
                          >
                            {item.read_error
                              ? "읽기 실패 · 상태 미확인"
                              : (statusLabel[item.status] || "확인 불가") +
                                ([
                                  "queued",
                                  "staged",
                                  "running",
                                  "loading",
                                  "preparing",
                                  "downloading",
                                  "verifying",
                                  "cancelling",
                                ].includes(item.status)
                                  ? " · 기록 당시 상태"
                                  : "")}
                          </span>
                        </td>
                        <td>
                          {formatTime(item.sort_at, preferences.time_display)}
                          <small>
                            {item.time_basis === "finished_at"
                              ? "완료·점검 시각 기준"
                              : item.time_basis === "started_at"
                                ? "시작 시각 기준"
                                : "원본에 유효한 시각 없음"}
                          </small>
                        </td>
                        <td>
                          <button
                            aria-label={
                              item.label + " " + item.id + " 상세 확인"
                            }
                            onClick={() => detail(item.kind, item.id)}
                          >
                            기록 상세 <ArrowRight size={15} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <div className="history-pagination">
              <button
                onClick={() =>
                  setOffset((n) =>
                    Math.max(0, n - preferences.history_page_size),
                  )
                }
                disabled={busy || offset === 0}
              >
                이전 페이지
              </button>
              <span>
                {data.total
                  ? `${offset + 1}–${Math.min(offset + data.items.length, data.total)} / ${data.total}`
                  : "0개"}
              </span>
              <button
                onClick={() =>
                  setOffset((n) => n + preferences.history_page_size)
                }
                disabled={busy || !data.has_more}
              >
                다음 페이지
              </button>
            </div>
          </>
        )}
      </section>
      {detailError && (
        <p className="banner danger" role="alert">
          {detailError}
        </p>
      )}
      {selected && (
        <section
          className="panel history-detail"
          aria-labelledby="history-detail-heading"
        >
          <div className="tts-card-heading">
            <h2 id="history-detail-heading" tabIndex={-1} ref={heading}>
              {selected.label} · 원본 기록 상세
            </h2>
            <button
              onClick={() => {
                setSelected(null);
                const view = appViewParams();
                view.delete("h_selected");
                replaceAppView(view);
              }}
            >
              상세 닫기
            </button>
          </div>
          <p>
            <code>
              {selected.source_id_available === false
                ? "원본 ID 형식 확인 필요"
                : selected.id}
            </code>
          </p>
          <p>
            종류 {kinds[selected.kind]} ·{" "}
            {selected.read_error
              ? "읽기 실패 · 원본 상태 미확인"
              : statusLabel[selected.status]}{" "}
            ·{" "}
            {selected.scope === "current_state"
              ? "현재 선택된 런타임의 상태 기록"
              : "저장된 과거 이력"}
          </p>
          <dl className="workspace-paths">
            <div>
              <dt>시작</dt>
              <dd>
                {formatTime(selected.started_at, preferences.time_display)}
              </dd>
            </div>
            <div>
              <dt>완료·점검</dt>
              <dd>
                {formatTime(selected.finished_at, preferences.time_display)}
              </dd>
            </div>
            {Object.entries(selected.details)
              .filter(([key]) => key !== "metrics")
              .map(([key, value]) => (
                <div key={key}>
                  <dt>{detailLabels[key] || key}</dt>
                  <dd>
                    <code>
                      {value === null
                        ? "미확인"
                        : Array.isArray(value)
                          ? value.join(" / ")
                          : typeof value === "boolean"
                            ? value
                              ? "확인됨"
                              : "확인되지 않음"
                            : String(value)}
                    </code>
                  </dd>
                </div>
              ))}
          </dl>
          {selected.has_error && (
            <p className="workspace-caveat">
              원본 작업이 오류를 기록했습니다. 개인정보가 포함될 수 있는 원시
              오류·로그 본문은 표시하지 않습니다.
            </p>
          )}
          {selected.read_error ? (
            <p className="banner" role="status">
              원본 파일을 읽지 못했습니다. 다른 기록은 계속 조회할 수 있습니다.
              파일을 자동 복구하거나 성공으로 바꾸지 않았습니다.
            </p>
          ) : (
            <>
              <div className="history-source-links">
                {selected.kind === "comparison" &&
                  Array.isArray(selected.details.run_ids) &&
                  selected.details.run_ids.map((id) => (
                    <button
                      key={String(id)}
                      onClick={() => detail("run", String(id))}
                    >
                      하위 실행 {String(id).slice(0, 8)} 확인
                    </button>
                  ))}
                {selected.kind === "run" &&
                  typeof selected.details.comparison_id === "string" && (
                    <button
                      onClick={() =>
                        detail(
                          "comparison",
                          String(selected.details.comparison_id),
                        )
                      }
                    >
                      부모 A/B 비교 기록
                    </button>
                  )}
                <button onClick={() => onSource(selected.kind, selected.id)}>
                  {selected.kind === "model_run" ||
                  selected.kind === "run" ||
                  selected.kind === "comparison" ||
                  selected.kind === "scan"
                    ? "이 원본 ID의 작업 화면"
                    : "관련 관리 화면 · 현재 상태"}{" "}
                  <ArrowRight size={15} />
                </button>
              </div>
              {selected.kind === "task" && (
                <p className="muted">
                  표시한 상태는 기록 당시의 상태이며 현재 활성 작업을 확인하는
                  표시는 아닙니다. 앱 작업 완료는 연결·수집·준비의 상위 작업
                  상태입니다. 하위 수집의 부분 실패나 실제 추론 성공을 대신하지
                  않습니다.
                </p>
              )}
              {selected.kind === "comparison" && (
                <PerformanceChart
                  comparisonId={selected.id}
                  preferences={preferences}
                  refreshKey={selected.status}
                  onRun={(id) => detail("run", id)}
                />
              )}
            </>
          )}
        </section>
      )}
    </div>
  );
}
