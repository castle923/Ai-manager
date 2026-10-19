import { appViewParams, replaceAppView } from "./workspace";
import { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Boxes,
  Search,
  RefreshCw,
  Database,
  ShieldCheck,
  ArrowUpRight,
  Folder,
  File,
  X,
  ChevronLeft,
  ChevronRight,
  SlidersHorizontal,
  Link2,
  CircleHelp,
  Check,
  AlertTriangle,
  Clock,
  HardDrive,
  Command,
  Layers,
  ArrowRight,
  Play,
  Settings2,
} from "lucide-react";
import "./style.css";
import { PreparationPanel } from "./PreparationPanel";
import { TaskPanel } from "./TaskPanel";
import { TtsPanel } from "./TtsPanel";
import { ComparisonPanel } from "./ComparisonPanel";
import { DesktopRuntime, TaskRuntime } from "./DesktopHost";
import { RegistryPanel, type CandidateRegistration } from "./RegistryPanel";
import { HistoryPanel } from "./HistoryPanel";
import { ValidationPanel } from "./ValidationPanel";
import { SettingsPanel } from "./SettingsPanel";
import {
  defaultPreferences,
  workspaceApi,
  type PreferenceRecord,
} from "./workspace";

type Scan = {
  scan_id: string;
  account: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  files_count: number;
  errors: string[];
};
type Item = {
  id: string;
  scan_id: string;
  name: string;
  path: string;
  account: string;
  family: string;
  scan_status: string;
  count?: number;
  kind?: string;
  size: number | null;
  modified?: string | null;
  format?: string;
  observations?: {
    weight_files: number;
    config_observed: boolean;
    tokenizer_observed: boolean;
    shards_missing: number | null;
  };
  files?: Item[];
  supports_preparation?: boolean;
};
type Data = {
  rows: Item[];
  total: number;
  page: number;
  limit: number;
  scans: Scan[];
  families: string[];
  summary: {
    files: number;
    groups: number;
    weights: number;
    known_bytes: number;
    unknown_sizes: number;
  };
};
type Status = {
  accounts: Record<string, { credential_saved: boolean; roots: number }>;
  task: {
    status: string;
    action?: string;
    account?: string;
    error?: string;
    result?: { status?: string };
  };
  inventory: { scans: Scan[] };
};
const labels: Record<string, string> = {
  complete: "수집 완료",
  partial: "부분 수집",
  cancelled: "수집 취소",
  interrupted: "수집 중단",
  running: "수집 중",
  weight_candidate: "가중치 후보",
  model_component_candidate: "구성요소 후보",
  distribution_document_candidate: "배포 문서 후보",
  idle: "대기",
  finished: "작업 종료",
  failed: "작업 실패",
};
const actionLabels: Record<string, string> = {
  connect: "Google 로그인",
  refresh: "인증 갱신 확인",
  scan: "허용 폴더 수집",
  disconnect: "연결 해제",
  prepare: "선정 모델 준비",
  runtime_check: "별도 환경 점검",
};
const errorLabels: Record<string, string> = {
  not_connected: "로그인이 필요합니다.",
  operation_running: "다른 작업이 진행 중입니다.",
  refresh_failed_reconnect_required:
    "인증을 갱신하지 못했습니다. 다시 로그인하세요.",
  network_error: "네트워크 연결을 확인하세요.",
  http_403: "폴더 읽기 권한이 거부되었습니다.",
  consent_denied: "Google 권한 동의가 취소되었습니다.",
  authentication_cancelled: "로그인이 취소되었습니다.",
  authentication_timeout: "로그인 대기 시간이 지났습니다.",
  cancelled: "사용자가 수집을 취소했습니다.",
  incomplete_search: "Drive 검색이 일부만 완료됐습니다.",
  process_interrupted: "이전 실행에서 수집이 중단됐습니다.",
  operation_failed_check_connection:
    "작업을 완료하지 못했습니다. 연결 상태를 확인하세요.",
};
const err = (v: string) => errorLabels[v] || "확인이 필요한 오류 · " + v;
const bytes = (v: number | null | undefined) =>
  v == null
    ? "미수집"
    : new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 1 }).format(
        v /
          1024 **
            (v >= 1024 ** 4
              ? 4
              : v >= 1024 ** 3
                ? 3
                : v >= 1024 ** 2
                  ? 2
                  : v >= 1024
                    ? 1
                    : 0),
      ) +
      " " +
      (v >= 1024 ** 4
        ? "TiB"
        : v >= 1024 ** 3
          ? "GiB"
          : v >= 1024 ** 2
            ? "MiB"
            : v >= 1024
              ? "KiB"
              : "B");
const time = (v: string | null | undefined) =>
  v
    ? new Date(v).toLocaleString("ko-KR", {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "미수집";
async function api<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init);
  const d = await r.json();
  if (!r.ok) throw Error(err(d.error || "request_failed"));
  return d;
}

function App() {
  function sourceFromUrl() {
    const p = appViewParams(),
      kind = p.get("source_kind"),
      id = p.get("source_id");
    return kind &&
      id &&
      ["model_run", "run", "comparison", "scan"].includes(kind) &&
      p.get("section") ===
        (
          {
            model_run: "tasks",
            run: "tts",
            comparison: "comparison",
            scan: "library",
          } as Record<string, string>
        )[kind] &&
      /^[a-f0-9]{32}$/.test(id)
      ? { kind, id }
      : null;
  }
  const [registration, setRegistration] =
    useState<CandidateRegistration | null>(null);
  const [section, setSectionState] = useState(() => {
      const value = appViewParams().get("section");
      return value &&
        [
          "registry",
          "validation",
          "history",
          "settings",
          "library",
          "connections",
          "preparation",
          "tts",
          "tasks",
          "comparison",
        ].includes(value)
        ? value
        : "registry";
    }),
    [view, setView] = useState("models"),
    [q, setQ] = useState(""),
    [search, setSearch] = useState(""),
    [account, setAccount] = useState(""),
    [kind, setKind] = useState(""),
    [family, setFamily] = useState(""),
    [sort, setSort] = useState("name"),
    [scan, setScan] = useState(() => {
      const p = appViewParams(),
        id = p.get("source_id");
      return p.get("source_kind") === "scan" && id && /^[a-f0-9]{32}$/.test(id)
        ? id
        : "";
    }),
    [page, setPage] = useState(1),
    [data, setData] = useState<Data | null>(null),
    [status, setStatus] = useState<Status | null>(null),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [tick, setTick] = useState(0),
    [detail, setDetail] = useState<Item | null>(null),
    [detailLoading, setDetailLoading] = useState(false),
    [pending, setPending] = useState(false),
    [confirm, setConfirm] = useState("");
  const csrf = useRef(""),
    searchInput = useRef<HTMLInputElement>(null),
    dialog = useRef<HTMLDialogElement>(null),
    restore = useRef<HTMLElement | null>(null),
    request = useRef(0),
    detailRequest = useRef(0);
  const navigationUsed = useRef(
    [
      "registry",
      "validation",
      "history",
      "settings",
      "library",
      "connections",
      "preparation",
      "tts",
      "tasks",
      "comparison",
    ].includes(appViewParams().get("section") || ""),
  );
  const [preferences, setPreferences] = useState(defaultPreferences);
  const [sourceSelection, setSourceSelection] = useState<{
    kind: string;
    id: string;
  } | null>(sourceFromUrl);
  const [sourceUrlError, setSourceUrlError] = useState(() =>
    Boolean(
      (appViewParams().has("source_kind") ||
        appViewParams().has("source_id")) &&
        !sourceFromUrl(),
    ),
  );
  const [sourceOriginError, setSourceOriginError] = useState("");
  const [validatedSource, setValidatedSource] = useState<string | null>(null);
  const activeSourceKey =
    sourceSelection &&
    ((section === "tasks" && sourceSelection.kind === "model_run") ||
      (section === "tts" && sourceSelection.kind === "run") ||
      (section === "comparison" && sourceSelection.kind === "comparison") ||
      (section === "library" && sourceSelection.kind === "scan"))
      ? sourceSelection.kind + ":" + sourceSelection.id
      : null;
  useEffect(() => {
    let live = true;
    setSourceOriginError("");
    setValidatedSource(null);
    if (sourceSelection && activeSourceKey) {
      workspaceApi<{ item: { read_error: boolean } }>(
        "/api/history/" + sourceSelection.kind + "/" + sourceSelection.id,
      )
        .then((r) => {
          if (live) {
            if (r.item.read_error)
              setSourceOriginError(
                "지정한 원본 기록을 읽지 못했습니다. 다른 최신 기록으로 바꾸지 않았습니다.",
              );
            else setValidatedSource(activeSourceKey);
          }
        })
        .catch((e) => {
          if (live) setSourceOriginError(e.message);
        });
    }
    return () => {
      live = false;
    };
  }, [sourceSelection, activeSourceKey]);
  function setSection(value: string) {
    navigationUsed.current = true;
    setSectionState(value);
  }
  useEffect(() => {
    let live = true;
    workspaceApi<{ preferences: PreferenceRecord }>("/api/preferences")
      .then((r) => {
        if (live) {
          setPreferences(r.preferences.values);
          if (!navigationUsed.current)
            setSectionState(r.preferences.values.default_section);
        }
      })
      .catch(() => {});
    return () => {
      live = false;
    };
  }, []);
  useEffect(() => {
    const view = appViewParams();
    view.set("section", section);
    replaceAppView(view);
  }, [section]);
  useEffect(() => {
    const view = appViewParams();
    if (
      sourceSelection &&
      ((section === "tasks" && sourceSelection.kind === "model_run") ||
        (section === "tts" && sourceSelection.kind === "run") ||
        (section === "comparison" && sourceSelection.kind === "comparison") ||
        (section === "library" && sourceSelection.kind === "scan"))
    ) {
      view.set("source_kind", sourceSelection.kind);
      view.set("source_id", sourceSelection.id);
    } else {
      view.delete("source_kind");
      view.delete("source_id");
    }
    replaceAppView(view);
  }, [sourceSelection, section]);
  useEffect(() => {
    api<{ csrf: string }>("/api/session")
      .then((d) => (csrf.current = d.csrf))
      .catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    const timer = setTimeout(() => {
      setSearch(q);
      setPage(1);
    }, 220);
    return () => clearTimeout(timer);
  }, [q]);
  useEffect(() => {
    let live = true;
    async function poll() {
      try {
        const s = await api<Status>("/api/status");
        if (live) {
          setStatus((previous) => {
            if (
              previous &&
              JSON.stringify(previous.inventory) !== JSON.stringify(s.inventory)
            )
              setTick((t) => t + 1);
            return s;
          });
        }
      } catch (e) {
        if (live) setError((e as Error).message);
      }
    }
    poll();
    const timer = setInterval(poll, 1800);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    const id = ++request.current;
    setLoading(true);
    const params = new URLSearchParams({
      view,
      q: search,
      account,
      kind,
      family,
      sort,
      scan,
      page: String(page),
      limit: "24",
    });
    api<Data>("/api/dashboard?" + params, { signal: controller.signal })
      .then((d) => {
        if (id === request.current) {
          setData(d);
          setError("");
        }
      })
      .catch((e) => {
        if (e.name !== "AbortError" && id === request.current)
          setError(e.message);
      })
      .finally(() => {
        if (id === request.current) setLoading(false);
      });
    return () => controller.abort();
  }, [view, search, account, kind, family, sort, scan, page, tick]);
  useEffect(() => {
    function key(e: KeyboardEvent) {
      if (!dialog.current?.open && (e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault();
        searchInput.current?.focus();
      }
    }
    document.addEventListener("keydown", key);
    return () => document.removeEventListener("keydown", key);
  }, []);
  useEffect(() => {
    const old = document.body.style.overflow;
    if (detail || detailLoading) {
      document.body.style.overflow = "hidden";
      if (!dialog.current?.open) dialog.current?.showModal();
    } else if (dialog.current?.open) {
      dialog.current.close();
      restore.current?.focus();
    }
    return () => {
      document.body.style.overflow = old;
    };
  }, [detail, detailLoading]);
  async function open(item: Item) {
    restore.current = document.activeElement as HTMLElement;
    const id = ++detailRequest.current;
    setDetail(null);
    setDetailLoading(true);
    try {
      const result = await api<Item>(
        "/api/detail?" +
          new URLSearchParams({ id: item.id, scan: item.scan_id }),
      );
      if (id === detailRequest.current) setDetail(result);
    } catch (e) {
      if (id === detailRequest.current) setError((e as Error).message);
    } finally {
      if (id === detailRequest.current) setDetailLoading(false);
    }
  }
  function close() {
    detailRequest.current++;
    setDetail(null);
    setDetailLoading(false);
  }
  async function act(action: string, a?: string) {
    if (!csrf.current) return;
    setPending(true);
    setError("");
    try {
      await api("/api/action", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-AiManager-CSRF": csrf.current,
        },
        body: JSON.stringify({ action, account: a }),
      });
      setTick((t) => t + 1);
      const s = await api<Status>("/api/status");
      setStatus(s);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPending(false);
      setConfirm("");
    }
  }
  function reset() {
    setQ("");
    setSearch("");
    setAccount("");
    setKind("");
    setFamily("");
    setScan("");
    setPage(1);
  }
  const busy = pending || status?.task.status === "running";
  const summary = data?.scans.length ? data.summary : undefined;
  const currentScans = data?.scans || [];
  const partial = currentScans.some((s) => s.status !== "complete");
  const activeFilters = Boolean(q || account || kind || family || scan);
  return (
    <div className="app-shell">
      <a className="skip" href="#main">
        본문으로 이동
      </a>
      <aside className="sidebar">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setSection("library");
          }}
        >
          <span className="brand-icon">
            <Boxes size={23} />
          </span>
          <span>
            ai<span className="brand-light">manager</span>
            <small>PERSONAL MODEL HUB</small>
          </span>
        </a>
        <p className="nav-label">내 라이브러리</p>
        <nav aria-label="주 탐색">
          <button className={section === "validation" ? "nav active" : "nav"} onClick={() => setSection("validation")}><ShieldCheck size={19} />자동 검수</button>
          <button
            className={section === "registry" ? "nav active" : "nav"}
            onClick={() => setSection("registry")}
          >
            <Boxes size={19} />
            모델 관리
          </button>
          <button
            className={section === "library" ? "nav active" : "nav"}
            onClick={() => setSection("library")}
          >
            <Layers size={19} />
            파일 후보 탐색
            <ArrowRight size={15} />
          </button>
          <button
            className={section === "connections" ? "nav active" : "nav"}
            onClick={() => setSection("connections")}
          >
            <Link2 size={19} />
            계정 및 수집
          </button>
          <button
            className={section === "preparation" ? "nav active" : "nav"}
            aria-label="선정 모델 준비"
            onClick={() => setSection("preparation")}
          >
            <HardDrive size={19} /> 모델 준비
          </button>
          <button
            className={section === "tts" ? "nav active" : "nav"}
            aria-label="음성 실행 작업실"
            onClick={() => setSection("tts")}
          >
            <Play size={19} /> 음성 작업실
          </button>
          <button
            className={section === "tasks" ? "nav active" : "nav"}
            onClick={() => setSection("tasks")}
          >
            <Play size={19} /> 유형별 작업실
          </button>
          <button
            className={section === "comparison" ? "nav active" : "nav"}
            onClick={() => setSection("comparison")}
          >
            <Layers size={19} /> 새 A/B 비교
          </button>
          <button
            className={section === "history" ? "nav active" : "nav"}
            onClick={() => setSection("history")}
          >
            <Database size={19} /> 통합 작업 기록
          </button>
          <button
            className={section === "settings" ? "nav active" : "nav"}
            onClick={() => setSection("settings")}
          >
            <Settings2 size={19} /> 설정
          </button>
        </nav>
        <div className="sidebar-note">
          <ShieldCheck size={20} />
          <strong>로컬 · 읽기 전용</strong>
          <p>
            허용한 폴더를 읽고 선정 모델을
            <br />이 PC에서 준비합니다.
          </p>
        </div>
        <div className="sidebar-foot">
          <span className="dot" /> 개인 PC에서 실행 중
          <small>M9 · 기록과 근거 연결</small>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <span>
            Ai-manager <span className="slash">/</span>{" "}
            {section === "validation" ? "보유 모델 자동 검수" : section === "tasks"
              ? "유형별 작업실"
              : section === "history"
                ? "통합 작업 기록"
                : section === "settings"
                  ? "설정"
                  : section === "registry"
                    ? "모델 관리"
                    : section === "library"
                      ? "파일 후보 탐색"
                      : section === "preparation"
                        ? "모델 준비"
                        : section === "tts"
                          ? "음성 작업실"
                          : section === "comparison"
                            ? "새 A/B 비교"
                            : "계정 및 수집"}
          </span>
          <div className="top-meta">
            <ShieldCheck size={15} /> Drive 읽기 전용{" "}
            <span className="avatar">ME</span>
          </div>
        </header>
        <main id="main">
          <DesktopRuntime />
          {sourceUrlError && (
            <div className="banner danger" role="alert">
              URL의 원본 종류와 ID를 확인하세요. 잘못된 선택을 최신 기록으로
              바꾸지 않았습니다.
              <button
                onClick={() => {
                  setSourceUrlError(false);
                  setSourceSelection(null);
                  setScan("");
                  setPage(1);
                }}
              >
                원본 선택 해제 후 일반 목록 보기
              </button>
            </div>
          )}
          {sourceOriginError && (
            <div className="banner danger" role="alert">
              {sourceOriginError}
              <button
                onClick={() => {
                  setSourceSelection(null);
                  setSourceOriginError("");
                  setScan("");
                  setPage(1);
                }}
              >
                원본 선택 해제 후 일반 목록 보기
              </button>
            </div>
          )}
          <div className="page-heading">
            <div>
              <div className="eyebrow">YOUR MODELS, CLEARLY ORGANIZED</div>
              <h1>
                {section === "validation" ? "보유 모델 자동 검수" : section === "tasks"
                  ? "유형별 작업실"
                  : section === "history"
                    ? "통합 작업 기록"
                    : section === "settings"
                      ? "작업실 설정"
                      : section === "registry"
                        ? "모델 관리"
                        : section === "library"
                          ? "파일 후보 탐색"
                          : section === "preparation"
                            ? "모델 준비"
                            : section === "tts"
                              ? "음성 작업실"
                              : section === "comparison"
                                ? "새 A/B 비교"
                                : "계정 및 수집"}
              </h1>
              <p>
                {section === "validation" ? "보유 모델 자동 검수" : section === "tasks"
                  ? "유형별 작업실"
                  : section === "history"
                    ? "수집부터 준비·실행·비교까지, 저장된 원본 기록과 확인 근거를 따라가세요."
                    : section === "settings"
                      ? "이 작업실의 보기 옵션과 자료 위치·적용 범위를 확인하세요."
                      : section === "registry"
                        ? "내 모델의 설명과 보관 위치를 등록하고, 확인된 근거에 따라 현재 상태를 살펴보세요."
                        : section === "library"
                          ? "흩어져 있는 모델 파일을 모으고, 현재 확인 수준을 한눈에 살펴보세요."
                          : section === "preparation"
                            ? "선정 모델의 파일과 환경을 준비하고, 확인 근거를 단계별로 살펴보세요."
                            : section === "tts"
                              ? "새 한국어 문장을 음성으로 만들고, 이번 실행의 검증 결과를 확인하세요."
                              : section === "comparison"
                                ? "같은 새 입력으로 두 모델을 실행하고, 실제 조건과 결과를 함께 비교하세요."
                                : "두 계정의 연결과 허용 폴더 수집을 관리하세요."}
              </p>
            </div>
            <button
              className="primary"
              onClick={() => {
                setSection("connections");
              }}
            >
              <RefreshCw size={17} /> 수집 관리
            </button>
          </div>
          {error && (
            <div className="banner danger" role="alert">
              <AlertTriangle size={19} />
              <span>{error}</span>
              <button onClick={() => setTick((t) => t + 1)}>
                다시 불러오기
              </button>
            </div>
          )}
          {status?.task.status === "running" && (
            <div className="banner" role="status">
              <RefreshCw className="spin" size={18} />
              <span>
                계정 {status.task.account} ·{" "}
                {actionLabels[status.task.action || ""] || "작업"} 진행
                중입니다. 진행 중인 작업은 아직 완료된 결과가 아닙니다.
              </span>
              <button onClick={() => act("cancel")} disabled={pending}>
                작업 취소
              </button>
            </div>
          )}
          {status?.task.status === "failed" && (
            <div className="banner danger" role="alert">
              <AlertTriangle size={18} />
              {err(status.task.error || "operation_failed_check_connection")}
            </div>
          )}
          {(sourceUrlError || sourceOriginError) &&
          ["tasks", "tts", "comparison", "library"].includes(section) ? (
            <section className="panel">
              <h2>원본 선택을 확인해야 합니다</h2>
              <p>
                잘못된 원본 ID가 지정돼 기록 화면을 열지 않았습니다. 위 버튼으로
                선택을 명시적으로 해제하거나 통합 작업 기록에서 원본을
                선택하세요.
              </p>
            </section>
          ) : activeSourceKey && validatedSource !== activeSourceKey ? (
            <section className="panel" role="status">
              지정한 원본 ID를 확인합니다. 최신 기록으로 바꾸어 표시하지
              않습니다.
            </section>
          ) : section === "validation" ? (
            <ValidationPanel csrf={csrf.current} />
          ) : section === "history" ? (
            <HistoryPanel
              preferences={preferences}
              onSource={(kind, id) => {
                setSourceSelection({ kind, id });
                if (kind === "scan") {
                  setScan(id);
                  setPage(1);
                }
                setSection(
                  kind === "model_run"
                    ? "tasks"
                    : kind === "run"
                      ? "tts"
                      : kind === "comparison"
                        ? "comparison"
                        : kind === "scan"
                          ? "library"
                          : kind === "task"
                            ? "connections"
                            : "preparation",
                );
              }}
            />
          ) : section === "settings" ? (
            <SettingsPanel csrf={csrf} onSaved={setPreferences} />
          ) : section === "registry" ? (
            <RegistryPanel
              csrf={csrf}
              candidate={registration}
              onCandidateUsed={() => setRegistration(null)}
              onExplore={() => setSection("library")}
              onTasks={() => setSection("tasks")}
              onPrepare={() => setSection("preparation")}
            />
          ) : section === "comparison" ? (
            <ComparisonPanel
              csrf={csrf}
              onPrepare={() => setSection("preparation")}
              initialComparisonId={
                sourceSelection?.kind === "comparison"
                  ? sourceSelection.id
                  : undefined
              }
              preferences={preferences}
            />
          ) : section === "tasks" ? (
            <>
              <TaskRuntime />
              <TaskPanel
                csrf={csrf.current}
                initialRunId={
                  sourceSelection?.kind === "model_run"
                    ? sourceSelection.id
                    : undefined
                }
              />
            </>
          ) : section === "tts" ? (
            <TtsPanel
              csrf={csrf}
              initialRunId={
                sourceSelection?.kind === "run" ? sourceSelection.id : undefined
              }
            />
          ) : section === "preparation" ? (
            <PreparationPanel
              busy={Boolean(busy)}
              canCancel={
                status?.task.status === "running" &&
                status?.task.action === "prepare"
              }
              csrf={csrf}
            />
          ) : section === "connections" ? (
            <>
              <div className="connection-grid">
                {["A", "B"].map((a) => (
                  <section className="connection-card" key={a}>
                    <div className="account-heading">
                      <span className="account-symbol">{a}</span>
                      <div>
                        <h2>계정 {a}</h2>
                        <p>
                          {status?.accounts[a].credential_saved
                            ? "자격 증명 저장됨"
                            : "연결이 필요합니다"}
                        </p>
                      </div>
                    </div>
                    <p className="muted">
                      저장된 자격 증명은 현재 인증 성공을 보장하지 않습니다.
                      갱신 확인으로 현재 연결을 검증하세요.
                    </p>
                    <dl className="connection-info">
                      <div>
                        <dt>승인된 폴더</dt>
                        <dd>{status?.accounts[a].roots ?? "미확인"}개</dd>
                      </div>
                      <div>
                        <dt>권한</dt>
                        <dd>Drive 읽기 전용</dd>
                      </div>
                    </dl>
                    <div className="connection-actions">
                      <button
                        className="primary"
                        disabled={busy}
                        onClick={() => act("scan", a)}
                      >
                        <RefreshCw size={16} /> 새로 수집
                      </button>
                      <button disabled={busy} onClick={() => act("refresh", a)}>
                        인증 갱신 확인
                      </button>
                      <button disabled={busy} onClick={() => act("connect", a)}>
                        Google 로그인
                      </button>
                      <button
                        className="subtle danger-text"
                        disabled={busy}
                        onClick={() => setConfirm(a)}
                      >
                        연결 해제
                      </button>
                    </div>
                    {confirm === a && (
                      <div className="banner danger">
                        <span>
                          이 PC의 계정 {a} 자격 증명을 지웁니다. 기존 수집
                          기록은 보존됩니다.
                        </span>
                        <button onClick={() => act("disconnect", a)}>
                          해제 확인
                        </button>
                        <button onClick={() => setConfirm("")}>취소</button>
                      </div>
                    )}
                  </section>
                ))}
              </div>
              <section className="panel history">
                <h2>수집 기록</h2>
                <p className="muted">
                  각 기록은 당시의 메타데이터 관찰입니다. 새 수집은 별도
                  기록으로 저장됩니다.
                </p>
                {status?.inventory.scans.length ? (
                  status.inventory.scans.map((s, i) => (
                    <button
                      className="history-row"
                      key={s.scan_id}
                      onClick={() => {
                        setScan(s.scan_id);
                        setPage(1);
                        setSection("library");
                      }}
                    >
                      <span className="account-chip">{s.account}</span>
                      <span>
                        <strong>{time(s.started_at)}</strong>
                        <small>
                          {s.scan_id.slice(0, 8)} ·{" "}
                          {i === 0 ? "가장 최근 기록" : "저장된 기록"}
                        </small>
                      </span>
                      <span>{s.files_count.toLocaleString()}개 파일</span>
                      <span
                        className={
                          "badge " +
                          (s.status === "complete" ? "green" : "amber")
                        }
                      >
                        {labels[s.status] || s.status}
                      </span>
                      <ArrowUpRight size={16} />
                    </button>
                  ))
                ) : (
                  <div className="empty">
                    <Database />
                    <h3>아직 수집 기록이 없습니다</h3>
                    <p>계정을 연결한 후 승인된 폴더를 새로 수집하세요.</p>
                  </div>
                )}
              </section>
            </>
          ) : (
            <>
              <div className="metric-grid">
                <Metric
                  title="발견한 후보 파일"
                  value={summary?.files}
                  icon={<File size={19} />}
                  note="계정별 관찰 · 중복 모델 수 아님"
                />
                <Metric
                  title="폴더별 후보 그룹"
                  value={summary?.groups}
                  icon={<Folder size={19} />}
                  note="같은 폴더의 파일 묶음"
                />
                <Metric
                  title="가중치 후보"
                  value={summary?.weights}
                  icon={<Database size={19} />}
                  note="파일명·확장자 기준 분류"
                />
                <Metric
                  title="관찰된 파일 크기"
                  text={
                    summary && summary.unknown_sizes < summary.files
                      ? bytes(summary.known_bytes)
                      : "미수집"
                  }
                  icon={<HardDrive size={19} />}
                  note={
                    summary?.unknown_sizes
                      ? `크기 미수집 ${summary.unknown_sizes}개 제외`
                      : "Drive 메타데이터 합계"
                  }
                />
              </div>
              <div className="evidence-strip">
                <span className="evidence-icon">
                  <ShieldCheck size={20} />
                </span>
                <div>
                  <strong>발견과 실행 준비는 서로 다른 상태입니다.</strong>
                  <p>
                    목록은 실제 Drive 메타데이터입니다. 구성 · 무결성 · 런타임 ·
                    실행 검증 결과는 모델 준비 화면에서 구분해 확인합니다.
                  </p>
                </div>
                <span className="badge neutral">조회용 MVP</span>
              </div>
              <div className="scan-strip">
                {["A", "B"].map((a) => {
                  const s = currentScans.find((s) => s.account === a);
                  return (
                    <div key={a}>
                      <span className="account-chip">{a}</span>
                      <span>
                        <strong>계정 {a}</strong>
                        <small>
                          {s
                            ? `${time(s.started_at)} · ${s.files_count}개 파일`
                            : "현재 선택 범위에 수집 기록 없음"}
                        </small>
                      </span>
                      <span
                        className={
                          "badge " +
                          (s?.status === "complete" ? "green" : "amber")
                        }
                      >
                        {s ? labels[s.status] || s.status : "미수집"}
                      </span>
                    </div>
                  );
                })}
              </div>
              {partial && (
                <div className="banner warning" role="status">
                  <AlertTriangle size={18} />
                  <span>
                    일부 수집이 완료되지 않았습니다. 현재 관찰된 파일만
                    표시하며, 누락된 파일이 있을 수 있습니다.{" "}
                    {currentScans
                      .flatMap((s) => s.errors)
                      .map(err)
                      .join(" · ")}
                  </span>
                </div>
              )}
              <section className="panel library">
                <div className="library-top">
                  <div className="tabs" role="group" aria-label="목록 보기">
                    <button
                      aria-pressed={view === "models"}
                      className={view === "models" ? "selected" : ""}
                      onClick={() => {
                        setView("models");
                        setPage(1);
                      }}
                    >
                      <Folder size={17} />
                      후보 그룹 <span>{summary?.groups ?? "–"}</span>
                    </button>
                    <button
                      aria-pressed={view === "files"}
                      className={view === "files" ? "selected" : ""}
                      onClick={() => {
                        setView("files");
                        setPage(1);
                      }}
                    >
                      <File size={17} />
                      전체 파일 <span>{summary?.files ?? "–"}</span>
                    </button>
                  </div>
                  <span className="live-note">
                    <span className="dot" />
                    {scan ? "선택한 수집 기록" : "계정별 최근 수집 기록"}
                  </span>
                </div>
                <div className="search-row">
                  <div className="search-field">
                    <Search size={19} />
                    <input
                      ref={searchInput}
                      aria-label="모델 이름 또는 경로 검색"
                      value={q}
                      onChange={(e) => setQ(e.target.value)}
                      placeholder="모델 이름, 경로 또는 용도로 검색"
                      maxLength={300}
                    />
                    {q ? (
                      <button
                        aria-label="검색어 지우기"
                        onClick={() => setQ("")}
                      >
                        <X size={16} />
                      </button>
                    ) : (
                      <kbd>Ctrl K</kbd>
                    )}
                  </div>
                  <label className="sort-label">
                    <span className="sr-only">정렬</span>
                    <select
                      aria-label="정렬"
                      value={sort}
                      onChange={(e) => {
                        setSort(e.target.value);
                        setPage(1);
                      }}
                    >
                      <option value="name">이름순</option>
                      <option value="size">큰 용량순</option>
                      <option value="modified">최근 수정순</option>
                    </select>
                  </label>
                </div>
                <div className="filters">
                  <SlidersHorizontal size={16} />
                  <label>
                    <span className="sr-only">계정 필터</span>
                    <select
                      aria-label="계정 필터"
                      value={account}
                      onChange={(e) => {
                        setAccount(e.target.value);
                        setPage(1);
                      }}
                    >
                      <option value="">모든 계정</option>
                      <option value="A">계정 A</option>
                      <option value="B">계정 B</option>
                    </select>
                  </label>
                  <label>
                    <span className="sr-only">용도 추정 필터</span>
                    <select
                      aria-label="용도 추정 필터"
                      value={family}
                      onChange={(e) => {
                        setFamily(e.target.value);
                        setPage(1);
                      }}
                    >
                      <option value="">모든 용도 (이름 추정)</option>
                      {data?.families.map((f) => (
                        <option key={f}>{f}</option>
                      ))}
                    </select>
                  </label>
                  <label>
                    <span className="sr-only">파일 종류 필터</span>
                    <select
                      aria-label="파일 종류 필터"
                      value={kind}
                      onChange={(e) => {
                        setKind(e.target.value);
                        setPage(1);
                      }}
                    >
                      <option value="">모든 파일 종류</option>
                      {Object.entries(labels)
                        .filter(([k]) => k.endsWith("candidate"))
                        .map(([k, v]) => (
                          <option value={k} key={k}>
                            {v}
                          </option>
                        ))}
                    </select>
                  </label>
                  <label className="snapshot-filter">
                    <span className="sr-only">수집 기록 선택</span>
                    <select
                      aria-label="수집 기록 선택"
                      value={scan}
                      onChange={(e) => {
                        setScan(e.target.value);
                        setPage(1);
                      }}
                    >
                      <option value="">계정별 최근 기록</option>
                      {status?.inventory.scans.map((s) => (
                        <option key={s.scan_id} value={s.scan_id}>
                          {s.account} · {time(s.started_at)} ·{" "}
                          {labels[s.status] || s.status}
                        </option>
                      ))}
                    </select>
                  </label>
                  {activeFilters && (
                    <button className="reset" onClick={reset}>
                      초기화 <X size={13} />
                    </button>
                  )}
                </div>
                <div className="result-meta" role="status" aria-live="polite">
                  <span>
                    {loading
                      ? "목록을 불러오는 중…"
                      : `${(data?.total ?? 0).toLocaleString()}개 ${view === "models" ? "후보 그룹" : "파일"}`}
                    {activeFilters ? " · 필터 적용됨" : ""}
                  </span>
                  <span>
                    {view === "models"
                      ? "폴더 기준으로 묶었으며, 독립 모델로 확정하지 않았습니다."
                      : "파일 내용은 내려받지 않았습니다."}
                  </span>
                </div>
                <div className="table-wrap" aria-busy={loading}>
                  <table>
                    <thead>
                      <tr>
                        <th scope="col">
                          {view === "models"
                            ? "후보 그룹 / 저장 위치"
                            : "파일 이름 / 저장 위치"}
                        </th>
                        <th scope="col">용도 추정</th>
                        <th scope="col">계정</th>
                        <th scope="col">
                          {view === "models" ? "구성 관찰" : "파일 종류"}
                        </th>
                        <th scope="col">파일 크기</th>
                        <th scope="col">확인 수준</th>
                        <th scope="col">
                          <span className="sr-only">상세</span>
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {data?.rows.map((item) => (
                        <tr key={item.id}>
                          <td>
                            <button
                              className="name-button"
                              onClick={() => open(item)}
                            >
                              <span
                                className={
                                  "file-icon " +
                                  (item.family === "음성 합성"
                                    ? "violet"
                                    : item.family === "언어 모델"
                                      ? "blue"
                                      : "")
                                }
                              >
                                {view === "models" ? (
                                  <Folder size={20} />
                                ) : (
                                  <File size={20} />
                                )}
                              </span>
                              <span className="name-content">
                                <strong title={item.name}>{item.name}</strong>
                                <small title={item.path}>{item.path}</small>
                              </span>
                            </button>
                          </td>
                          <td>
                            <span className="family-label">{item.family}</span>
                            <small className="cell-note">파일명 기준</small>
                          </td>
                          <td>
                            <span className="account-chip">{item.account}</span>
                          </td>
                          <td>
                            {view === "models" ? (
                              <>
                                <strong className="count">
                                  {item.count}개 파일
                                </strong>
                                <small className="cell-note">
                                  가중치 {item.observations?.weight_files}개
                                </small>
                              </>
                            ) : (
                              <>
                                <span className="family-label">
                                  {labels[item.kind || ""] || "미분류"}
                                </span>
                                <small className="cell-note">
                                  {item.format}
                                </small>
                              </>
                            )}
                          </td>
                          <td className="size-cell">{bytes(item.size)}</td>
                          <td>
                            <span
                              className={
                                "badge " +
                                (item.scan_status === "complete"
                                  ? "neutral"
                                  : "amber")
                              }
                            >
                              {item.scan_status === "complete"
                                ? "발견됨"
                                : labels[item.scan_status] || "부분 관찰"}
                            </span>
                            <small className="cell-note">실행 미확인</small>
                          </td>
                          <td>
                            <button
                              className="icon-button"
                              aria-label={item.name + " 상세 보기"}
                              onClick={() => open(item)}
                            >
                              <ArrowUpRight size={18} />
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {!loading && !data?.rows.length && (
                  <div className="empty">
                    <Search size={30} />
                    <h3>
                      {summary?.files
                        ? "조건에 맞는 항목이 없습니다"
                        : "아직 수집된 후보 파일이 없습니다"}
                    </h3>
                    <p>
                      {summary?.files
                        ? "검색어와 필터를 바꿔 다시 찾아보세요."
                        : "계정 및 수집에서 승인된 폴더를 새로 수집하세요."}
                    </p>
                    <button
                      onClick={
                        summary?.files ? reset : () => setSection("connections")
                      }
                    >
                      {summary?.files ? "필터 초기화" : "계정 및 수집 열기"}
                    </button>
                  </div>
                )}
                <div className="pagination">
                  <span>
                    {data?.total
                      ? `${((data.page - 1) * data.limit + 1).toLocaleString()}–${Math.min(data.page * data.limit, data.total).toLocaleString()} / ${data.total.toLocaleString()}개`
                      : "0개"}{" "}
                    <small>· 페이지당 24개</small>
                  </span>
                  <div>
                    <button
                      aria-label="이전 페이지"
                      disabled={loading || !data || data.page <= 1}
                      onClick={() => setPage((data?.page || 1) - 1)}
                    >
                      <ChevronLeft size={16} />
                    </button>
                    <span>
                      {data?.page || 1} /{" "}
                      {Math.max(1, Math.ceil((data?.total || 0) / 24))}
                    </span>
                    <button
                      aria-label="다음 페이지"
                      disabled={
                        loading || !data || data.page * data.limit >= data.total
                      }
                      onClick={() => setPage((data?.page || 1) + 1)}
                    >
                      <ChevronRight size={16} />
                    </button>
                  </div>
                </div>
              </section>
              <div className="bottom-note">
                <CircleHelp size={15} />
                <span>
                  용도는 이름·경로에서 추정합니다. 구성과 실행 가능 여부는 상세
                  화면의 확인 근거를 살펴보세요.
                </span>
              </div>
            </>
          )}
          <footer>
            AI-MANAGER{" "}
            <span>
              메타데이터를 읽고, 근거를 확인하고, 다음 단계를 준비합니다.
            </span>
            <span>LOCAL / READ ONLY</span>
          </footer>
        </main>
      </div>
      <dialog
        ref={dialog}
        className="detail-dialog"
        aria-labelledby="detail-title"
        onCancel={close}
        onKeyDown={(e) => {
          if (e.key === "Tab") {
            const nodes = dialog.current?.querySelectorAll<HTMLElement>(
              "button:not(:disabled),a[href],input,select",
            );
            if (nodes?.length) {
              const first = nodes[0],
                last = nodes[nodes.length - 1];
              if (e.shiftKey && document.activeElement === first) {
                e.preventDefault();
                last.focus();
              } else if (!e.shiftKey && document.activeElement === last) {
                e.preventDefault();
                first.focus();
              }
            }
          }
        }}
        onClick={(e) => {
          if (e.target === e.currentTarget) close();
        }}
      >
        <div className="detail-inner">
          <div className="detail-top">
            <span className="eyebrow">OBSERVATION DETAILS</span>
            <button
              className="icon-button"
              onClick={close}
              aria-label="상세 닫기"
              autoFocus
            >
              <X size={21} />
            </button>
          </div>
          {detailLoading ? (
            <div className="empty" role="status">
              <RefreshCw className="spin" />
              <p id="detail-title">상세를 불러오는 중…</p>
            </div>
          ) : (
            detail && (
              <>
                <div className="detail-title-icon">
                  <Folder size={25} />
                </div>
                <h2 id="detail-title">{detail.name}</h2>
                <p className="detail-path">{detail.path}</p>
                <div className="detail-badges">
                  <span className="account-chip">계정 {detail.account}</span>
                  <span className="badge neutral">
                    {detail.files ? "폴더별 후보 그룹" : "후보 파일"}
                  </span>
                  <span className="badge amber">실행 미확인</span>
                </div>
                <div className="detail-callout">
                  <button
                    className="primary"
                    onClick={() => {
                      setRegistration({
                        id: detail.id,
                        scan_id: detail.scan_id,
                        name: detail.name,
                        path: detail.path,
                        family: detail.family,
                      });
                      close();
                      setSection("registry");
                    }}
                  >
                    이 후보를 모델로 등록
                  </button>
                  <CircleHelp size={18} />
                  <p>
                    이 항목은 선택한 수집 기록의 파일 메타데이터에서
                    발견했습니다. 이 기록만으로 현재 로컬 파일이나 환경의 준비
                    상태를 판정하지 않습니다.
                  </p>
                </div>
                <div className="detail-prepare-link">
                  <HardDrive size={20} />
                  <div>
                    <strong>
                      {detail.supports_preparation
                        ? "첫 준비 대상 후보"
                        : "이 항목의 준비 어댑터는 미지원"}
                    </strong>
                    <p>
                      현재 준비 기능은 Qwen3-TTS 0.6B / 1.7B CustomVoice 모델에
                      제공됩니다. 준비 화면에서 선정 출처와 현재 검증 결과를
                      확인하세요.
                    </p>
                  </div>
                  <button
                    onClick={() => {
                      close();
                      setSection("preparation");
                    }}
                  >
                    준비 화면
                  </button>
                </div>
                <h3>이 수집 기록의 메타데이터 확인 수준</h3>
                <p className="caption">
                  이 수집 기록의 메타데이터만으로는 구성·무결성·환경·실행 상태를
                  판정하지 않습니다. 다운로드한 파일의 검증 결과는 모델 준비
                  화면에서 확인하세요.
                </p>
                <div className="verification-list">
                  {[
                    [
                      "발견",
                      labels[detail.scan_status] || detail.scan_status,
                      "Drive 메타데이터 관찰",
                    ],
                    [
                      "구성 충족",
                      "미확인",
                      "수집 메타데이터만으로 필수 구성 충족 판정 불가",
                    ],
                    [
                      "파일 무결성",
                      "미확인",
                      "메타데이터로 바이트·해시 검증 불가",
                    ],
                    [
                      "런타임 준비",
                      "미확인",
                      "수집 메타데이터만으로 현재 환경 상태 판정 불가",
                    ],
                    [
                      "실제 실행",
                      "미확인",
                      "메타데이터는 실제 출력의 검증 근거가 아님",
                    ],
                  ].map(([title, state, note], i) => (
                    <div key={title}>
                      <span
                        className={
                          "verification-icon " + (!i ? "observed" : "")
                        }
                      >
                        {!i ? <Check size={15} /> : <Clock size={15} />}
                      </span>
                      <div>
                        <strong>{title}</strong>
                        <small>{note}</small>
                      </div>
                      <span className={!i ? "observed-text" : "muted"}>
                        {state}
                      </span>
                    </div>
                  ))}
                </div>
                <h3>메타데이터 근거</h3>
                <dl className="detail-metadata">
                  <div>
                    <dt>용도 추정</dt>
                    <dd>
                      {detail.family} <small>이름·경로 기준</small>
                    </dd>
                  </div>
                  <div>
                    <dt>관찰된 크기</dt>
                    <dd>{bytes(detail.size)}</dd>
                  </div>
                  <div>
                    <dt>수집 시각</dt>
                    <dd>
                      {time(
                        status?.inventory.scans.find(
                          (s) => s.scan_id === detail.scan_id,
                        )?.started_at,
                      )}
                    </dd>
                  </div>
                  <div>
                    <dt>수집 기록</dt>
                    <dd className="mono">{detail.scan_id}</dd>
                  </div>
                  {detail.modified && (
                    <div>
                      <dt>Drive 수정 시각</dt>
                      <dd>{time(detail.modified)}</dd>
                    </div>
                  )}
                </dl>
                {detail.observations && (
                  <>
                    <h3>폴더 안에서 관찰된 구성</h3>
                    <div className="observation-grid">
                      <div>
                        <span>가중치 후보</span>
                        <strong>{detail.observations.weight_files}개</strong>
                      </div>
                      <div>
                        <span>Config 이름</span>
                        <strong>
                          {detail.observations.config_observed
                            ? "관찰됨"
                            : "관찰되지 않음"}
                        </strong>
                      </div>
                      <div>
                        <span>Tokenizer 이름</span>
                        <strong>
                          {detail.observations.tokenizer_observed
                            ? "관찰됨"
                            : "관찰되지 않음"}
                        </strong>
                      </div>
                      <div>
                        <span>분할 파일 번호</span>
                        <strong>
                          {detail.observations.shards_missing === null
                            ? "판별 근거 없음"
                            : detail.observations.shards_missing
                              ? `관찰상 ${detail.observations.shards_missing}개 부족`
                              : "관찰상 번호 일치"}
                        </strong>
                      </div>
                    </div>
                    <p className="caption">
                      파일명 관찰입니다. Config·Tokenizer가 필요한 모델인지,
                      분할 파일 내용과 인덱스가 일치하는지는 미확인입니다.
                    </p>
                  </>
                )}
                {detail.files && (
                  <>
                    <h3>
                      후보 파일{" "}
                      <span className="muted">{detail.files.length}</span>
                    </h3>
                    <div className="detail-files">
                      {detail.files.map((f) => (
                        <div key={f.id}>
                          <File size={16} />
                          <span title={f.name}>
                            {f.name}
                            <small>{labels[f.kind || ""]}</small>
                          </span>
                          <strong>{bytes(f.size)}</strong>
                        </div>
                      ))}
                    </div>
                  </>
                )}
                <div className="detail-footer">
                  <ShieldCheck size={17} />
                  <span>
                    모델 발견과 준비·실행 검증은 서로 다른 확인 단계입니다.
                  </span>
                </div>
              </>
            )
          )}
        </div>
      </dialog>
    </div>
  );
}
function Metric({
  title,
  value,
  text,
  icon,
  note,
}: {
  title: string;
  value?: number;
  text?: string;
  icon: React.ReactNode;
  note: string;
}) {
  return (
    <section className="metric">
      <div>
        <span>{title}</span>
        <span className="metric-icon">{icon}</span>
      </div>
      <strong>
        {text ?? (value === undefined ? "미수집" : value.toLocaleString())}
      </strong>
      <p>{note}</p>
    </section>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
