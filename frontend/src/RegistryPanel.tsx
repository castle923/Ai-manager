import { useEffect, useRef, useState, type RefObject } from "react";
import { AudioDownload } from "./DesktopHost";
import {
  Boxes,
  Check,
  CircleHelp,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
} from "lucide-react";

export type CandidateRegistration = {
  id: string;
  scan_id: string;
  name: string;
  path: string;
  family: string;
};
type Metadata = {
  name: string;
  type: string;
  description: string;
  version_label: string;
  tags: string[];
  notes: string;
};
type Artifact = {
  adapter_id: string;
  revision: string;
  manifest_sha256?: string;
};
type Reference = {
  kind: string;
  identity: string;
  path: string;
  account?: string;
  scan_id?: string;
  components: { name: string; size?: number; kind: string; sha256?: string }[];
  observation_status: string;
  artifact_match?: boolean;
  checked_at?: string;
};
type Run = {
  id: string;
  status: string;
  error: string | null;
  audio_url: string | null;
  model: { name: string };
  output?: { duration_seconds: number; sha256: string };
  metrics?: { total_seconds?: number; peak_gpu_allocated_bytes?: number };
};
type Model = {
  id: string;
  row_version: number;
  created_at: string;
  updated_at: string;
  metadata: Metadata;
  artifact: Artifact;
  references: Reference[];
  archived: boolean;
  status: string;
  execution: string;
  preparation: string;
  integrity: string;
  runtime: string;
  latest_run_status: string | null;
  configuration_attention: boolean;
  configuration_reasons: string[];
  generation: string;
  fingerprint: string;
  runs: { run: Run; current_artifact: boolean; verified: boolean }[];
};
type Data = {
  models: Model[];
  summary: {
    registered: number;
    verified: number;
    configuration_needed: number;
  };
  supported_artifacts: { adapter_id: string; name: string; revision: string }[];
};
const statusLabels: Record<string, string> = {
  ready: "실행 준비 확인",
  prepared: "준비 기록 확인",
  configuration_needed: "구성 확인 필요",
  unexecuted: "미실행",
  verified: "실행 검증 완료",
  failed: "실행 실패",
  running: "실행 중",
  archived: "보관됨",
  unverified: "실행 미검증",
  succeeded: "생성 완료",
  queued: "실행 대기",
  preparing: "파일 확인 중",
  loading: "모델 로딩 중",
  cancelled: "취소됨",
  interrupted: "중단됨",
  cancelling: "취소 중",
};
const reasons: Record<string, string> = {
  references_unconfirmed: "보관 위치 미등록",
  configuration_unconfirmed: "모델 구성 미확인 · 실행 어댑터 미지원",
  local_location_unavailable: "로컬 폴더 접근 미확인",
  reference_out_of_scope: "현재 허용 범위 밖 참조",
  artifact_revision_changed: "지정 구성 버전이 바뀌었습니다",
  artifact_files_unconfirmed:
    "고정 구성과 일치하는 로컬 파일의 해시를 확인해야 합니다",
};
const errors: Record<string, string> = {
  stale_edit:
    "다른 변경이 저장되었습니다. 현재 값을 다시 불러온 후 편집하세요.",
  duplicate_reference: "이미 등록된 보관 위치입니다. 해당 모델을 편집하세요.",
  name_required: "모델 이름을 입력하세요.",
  unsupported_artifact: "현재 지원하는 고정 구성 버전을 선택하세요.",
  adapter_unsupported: "이 모델 종류는 아직 실행을 지원하지 않습니다.",
  configuration_required: "보관 위치와 구성을 먼저 확인하세요.",
  reference_out_of_scope: "현재 허용된 수집 범위의 후보를 선택하세요.",
  candidate_not_found: "후보 기록을 찾지 못했습니다. 후보를 다시 선택하세요.",
  operation_running: "다른 앱이 작업 큐를 사용하고 있습니다.",
  queue_full: "작업 큐가 가득 찼습니다.",
  invalid_local_reference:
    "전체 절대 경로를 입력하세요. 링크·재분석 경로는 허용하지 않습니다.",
  local_directory_missing: "선택한 로컬 폴더를 찾지 못했습니다.",
};
const blank = (): Metadata => ({
  name: "",
  type: "미분류",
  description: "",
  version_label: "",
  tags: [],
  notes: "",
});
Object.assign(errors, {
  artifact_files_changed:
    "등록한 자산의 파일이 바뀌었습니다. 보관 참조를 다시 확인하세요.",
  registered_artifact_mismatch:
    "등록한 원본과 준비한 모델의 구성이 일치하지 않습니다.",
  reference_scope_ambiguous:
    "수집 폴더 별칭이 중복되어 출처를 확인할 수 없습니다.",
  candidate_reference_ambiguous:
    "이 후보는 보관 폴더를 확정할 수 없습니다. 개별 파일 후보를 선택하세요.",
  invalid_references: "보관 참조를 확인하세요.",
  text_required: "새 한국어 문장을 입력하세요.",
  text_too_long: "문장은 300자 이내로 입력하세요.",
  model_not_ready: "모델 파일 준비를 먼저 완료하세요.",
  runtime_not_ready: "추론 환경 준비와 환경 점검을 완료하세요.",
  model_integrity_failed:
    "모델 파일이 지정 구성과 다릅니다. 무결성을 다시 확인하세요.",
  model_archived: "보관한 모델은 실행할 수 없습니다.",
  output_invalid: "생성한 WAV 검증을 완료하지 못했습니다.",
  timeout: "제한 시간 안에 실행을 완료하지 못했습니다.",
});

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  const data = await response.json();
  if (!response.ok)
    throw new Error(
      errors[data.error] ||
        "요청을 완료하지 못했습니다. 입력과 연결 상태를 확인하세요.",
    );
  return data;
}

export function RegistryPanel({
  csrf,
  candidate,
  onCandidateUsed,
  onExplore,
  onPrepare,
}: {
  csrf: RefObject<string>;
  candidate: CandidateRegistration | null;
  onCandidateUsed: () => void;
  onExplore: () => void;
  onPrepare: () => void;
}) {
  const [data, setData] = useState<Data | null>(null),
    [selected, setSelected] = useState<Model | null>(null),
    [editing, setEditing] = useState(false);
  const [editBase, setEditBase] = useState<Model | null>(null);
  const [metadata, setMetadata] = useState<Metadata>(blank),
    [artifact, setArtifact] = useState<Artifact>({
      adapter_id: "",
      revision: "",
    }),
    [tagText, setTagText] = useState("");
  const [newCandidate, setNewCandidate] =
      useState<CandidateRegistration | null>(null),
    [local, setLocal] = useState(""),
    [replaceRefs, setReplaceRefs] = useState(false);
  const [search, setSearch] = useState(""),
    [filter, setFilter] = useState(""),
    [archived, setArchived] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [message, setMessage] = useState(""),
    [text, setText] = useState("");
  const [modelType, setModelType] = useState("");
  const [tick, setTick] = useState(0);
  const selection = useRef(""),
    heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    const controller = new AbortController();
    let live = true;
    let inflight = false;
    async function load() {
      if (inflight) return;
      inflight = true;
      try {
        const result = await request<Data>(
          "/api/registry?" +
            new URLSearchParams({
              q: search,
              status: filter,
              archived: archived ? "1" : "0",
            }),
          { signal: controller.signal },
        );
        if (live) setData(result);
        const target = selection.current;
        if (target) {
          const detail = await request<{ model: Model }>(
            "/api/registry/" + target,
            { signal: controller.signal },
          );
          if (live && selection.current === target)
            setSelected((old) =>
              old?.id === detail.model.id ? detail.model : old,
            );
        }
      } catch (e) {
        if (live && (e as Error).name !== "AbortError")
          setError((e as Error).message);
      } finally {
        inflight = false;
      }
    }
    void load();
    const timer = setInterval(load, 3000);
    return () => {
      live = false;
      controller.abort();
      clearInterval(timer);
    };
  }, [search, filter, archived, tick]);
  useEffect(() => {
    if (!candidate) return;
    selection.current = "";
    setSelected(null);
    setEditBase(null);
    setEditing(true);
    setMetadata({ ...blank(), name: candidate.name, type: candidate.family });
    setTagText("");
    setArtifact({ adapter_id: "", revision: "" });
    setNewCandidate(candidate);
    setLocal("");
    setReplaceRefs(false);
    setError("");
    setMessage("선택한 후보의 관측 정보를 참조해 모델을 등록합니다.");
    onCandidateUsed();
  }, [candidate, onCandidateUsed]);
  function choose(model: Model) {
    selection.current = model.id;
    setSelected(model);
    setEditing(false);
    setError("");
    setMessage("");
    setTick((t) => t + 1);
    requestAnimationFrame(() => heading.current?.focus());
  }
  function edit(model: Model | null) {
    setEditBase(model);
    setEditing(true);
    setMetadata(model ? { ...model.metadata } : blank());
    setTagText(model?.metadata.tags.join(", ") || "");
    setArtifact(
      model
        ? {
            adapter_id: model.artifact.adapter_id,
            revision: model.artifact.revision,
          }
        : { adapter_id: "", revision: "" },
    );
    setLocal("");
    setNewCandidate(null);
    setReplaceRefs(false);
    setError("");
    setMessage("");
    if (!model) {
      selection.current = "";
      setSelected(null);
    }
  }
  async function mutate(url: string, body: unknown) {
    return request<{ model: Model }>(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-AiManager-CSRF": csrf.current,
      },
      body: JSON.stringify(body),
    });
  }
  async function save() {
    if (busy || !csrf.current) return;
    setBusy(true);
    setError("");
    setMessage("모델 구성과 지정 파일의 해시를 확인하고 저장합니다…");
    try {
      const refs: unknown[] = newCandidate
        ? [{ candidate_id: newCandidate.id, scan_id: newCandidate.scan_id }]
        : editBase && !replaceRefs
          ? editBase.references.map((ref) => ({ existing_identity: ref.identity }))
          : [];
      if (local.trim()) refs.push({ local_directory: local.trim() });
      const body = {
        metadata: {
          ...metadata,
          tags: tagText
            .split(",")
            .map((t) => t.trim())
            .filter(Boolean),
        },
        artifact,
        references: refs,
      };
      const result = await mutate(
        "/api/registry" + (editBase ? "/" + editBase.id : ""),
        editBase
          ? {
              ...body,
              row_version: editBase.row_version,
              archived: editBase.archived,
            }
          : body,
      );
      choose(result.model);
      setMessage(
        "모델 정보를 저장했습니다. 파일을 이동하거나 수정하지 않았습니다.",
      );
    } catch (e) {
      setMessage("");
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function archiveModel() {
    if (!selected || busy) return;
    setBusy(true);
    setError("");
    try {
      const result = await mutate("/api/registry/" + selected.id, {
        row_version: selected.row_version,
        metadata: selected.metadata,
        artifact: {
          adapter_id: selected.artifact.adapter_id,
          revision: selected.artifact.revision,
        },
        references: selected.references.map((ref) => ({ existing_identity: ref.identity })),
        archived: !selected.archived,
      });
      choose(result.model);
      setMessage(
        result.model.archived
          ? "목록에서 보관했습니다. 원본 파일과 실행 기록은 보존됩니다."
          : "모델을 다시 활성화했습니다. 현재 구성은 새 실행으로 다시 검증하세요.",
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function run() {
    if (!selected || busy || !text.trim()) return;
    setBusy(true);
    setError("");
    setMessage("등록한 원본의 파일 해시를 확인하고 새 실행을 준비합니다…");
    try {
      await request("/api/registry/" + selected.id + "/runs", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-AiManager-CSRF": csrf.current,
        },
        body: JSON.stringify({ row_version: selected.row_version, text }),
      });
      setMessage("현재 모델 구성에 연결한 새 실행을 요청했습니다.");
      setText("");
      setTick((t) => t + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function cancelRun(id: string) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await request("/api/tts/runs/" + id + "/cancel", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-AiManager-CSRF": csrf.current,
        },
        body: "{}",
      });
      setMessage("이 실행의 취소를 요청했습니다.");
      setTick((t) => t + 1);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const visibleModels =
    data?.models.filter((m) => !modelType || m.metadata.type === modelType) ||
    [];
  const hasFilter = Boolean(search || filter || modelType);
  return (
    <section className="registry-panel" aria-label="등록 모델 관리">
      <div className="registry-kpis">
        {[
          ["등록 모델", data?.summary.registered, Boxes],
          ["실행 검증 완료", data?.summary.verified, ShieldCheck],
          ["구성 확인 필요", data?.summary.configuration_needed, CircleHelp],
        ].map(([label, value, Icon]) => {
          const Symbol = Icon as typeof Boxes;
          return (
            <article key={String(label)} className="registry-kpi">
              <Symbol size={21} />
              <span>{String(label)}</span>
              <strong>{value === undefined ? "—" : String(value)}</strong>
            </article>
          );
        })}
      </div>
      <p className="caption">
        보관하지 않은 모델 단위 집계입니다. 파일 후보는 포함하지 않습니다. 구성
        미확인·부족은 확인 필요에 포함하며, 실행 실패는 별도로 표시합니다.
      </p>
      <div className="registry-toolbar">
        <label className="registry-search">
          <Search size={17} />
          <span className="sr-only">등록 모델 검색</span>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="모델 이름, 용도, 태그 검색"
            maxLength={300}
          />
        </label>
        <label>
          상태
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="">모든 상태</option>
            {[
              "unexecuted",
              "prepared",
              "ready",
              "configuration_needed",
              "verified",
              "running",
              "failed",
              "archived",
            ].map((s) => (
              <option key={s} value={s}>
                {statusLabels[s]}
              </option>
            ))}
          </select>
        </label>
        <label>
          용도
          <select
            value={modelType}
            onChange={(e) => setModelType(e.target.value)}
          >
            <option value="">모든 용도</option>
            {Array.from(new Set(data?.models.map((m) => m.metadata.type) || []))
              .sort()
              .map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
          </select>
        </label>
        <label className="registry-check">
          <input
            type="checkbox"
            checked={archived}
            onChange={(e) => setArchived(e.target.checked)}
          />
          보관 모델 포함
        </label>
        <button
          onClick={() => setTick((t) => t + 1)}
          aria-label="모델 목록 새로고침"
        >
          <RefreshCw size={16} />
        </button>
        <button className="primary" onClick={() => edit(null)} disabled={busy}>
          <Plus size={16} />
          모델 등록
        </button>
      </div>
      {error ? (
        <div className="banner danger" role="alert">
          {error}
          {editing && selected ? (
            <button
              onClick={() => {
                setEditing(false);
                setTick((t) => t + 1);
              }}
            >
              현재 값 다시 불러오기
            </button>
          ) : null}
        </div>
      ) : null}
      {message ? (
        <p role="status" className="registry-notice">
          {message}
        </p>
      ) : null}
      <div className="registry-layout">
        <div className="registry-list panel">
          <div className="section-title">
            <h2>등록 모델</h2>
            <button onClick={onExplore}>파일 후보에서 등록</button>
          </div>
          {!data ? (
            <p className="empty">등록 목록을 불러오는 중입니다.</p>
          ) : visibleModels.length === 0 ? (
            <div className="empty">
              <Boxes size={28} />
              <h3>
                {hasFilter
                  ? "검색 조건에 맞는 모델이 없습니다"
                  : "등록된 모델이 없습니다"}
              </h3>
              <p>
                {hasFilter
                  ? "검색어나 상태·용도 조건을 변경하세요."
                  : "모델을 직접 등록하거나 파일 후보를 선택하세요. 발견한 파일이 자동 등록되지는 않습니다."}
              </p>
              {hasFilter ? (
                <button
                  onClick={() => {
                    setSearch("");
                    setFilter("");
                    setModelType("");
                  }}
                >
                  검색 조건 초기화
                </button>
              ) : null}
            </div>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>모델 / 용도</th>
                    <th>보관 위치</th>
                    <th>현재 확인 수준</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleModels.map((m) => (
                    <tr
                      key={m.id}
                      className={
                        selected?.id === m.id ? "registry-selected" : ""
                      }
                    >
                      <td>
                        <button
                          disabled={busy}
                          className="registry-model-name"
                          onClick={() => choose(m)}
                          aria-pressed={selected?.id === m.id}
                        >
                          {m.metadata.name}
                        </button>
                        <small>
                          {m.metadata.type} ·{" "}
                          {m.metadata.version_label || "표시 버전 미입력"}
                        </small>
                      </td>
                      <td>
                        {m.references.length ? (
                          m.references.map((r) => (
                            <span key={r.identity} className="badge neutral">
                              {r.account ? "Drive " + r.account : "로컬"}
                            </span>
                          ))
                        ) : (
                          <span className="caption">미등록</span>
                        )}
                      </td>
                      <td>
                        <span
                          className={
                            "badge " +
                            (m.status === "verified"
                              ? "green"
                              : m.status === "configuration_needed" ||
                                  m.status === "failed"
                                ? "amber"
                                : "neutral")
                          }
                        >
                          {statusLabels[m.status]}
                        </span>
                        {m.latest_run_status === "failed" &&
                        m.status !== "failed" ? (
                          <small>최근 실행 실패</small>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
        <aside className="registry-detail panel" aria-label="등록 모델 상세">
          {editing ? (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void save();
              }}
            >
              <h2 ref={heading} tabIndex={-1}>
                {selected ? "모델 정보 편집" : "새 모델 등록"}
              </h2>
              <p className="caption">
                관리 정보는 자유롭게 편집할 수 있습니다. 실행 대상 구성·보관
                참조 변경 시 현재 검증이 해제됩니다.
              </p>
              <fieldset disabled={busy}>
                <label>
                  모델 이름 *
                  <input
                    required
                    maxLength={200}
                    value={metadata.name}
                    onChange={(e) =>
                      setMetadata((m) => ({ ...m, name: e.target.value }))
                    }
                  />
                </label>
                <div className="registry-form-row">
                  <label>
                    용도
                    <input
                      maxLength={200}
                      list="registry-types"
                      value={metadata.type}
                      onChange={(e) =>
                        setMetadata((m) => ({ ...m, type: e.target.value }))
                      }
                    />
                    <datalist id="registry-types">
                      {[
                        "음성 합성",
                        "음성 인식",
                        "이미지 생성",
                        "언어 모델",
                        "영상 추적",
                        "미분류",
                      ].map((t) => (
                        <option key={t} value={t} />
                      ))}
                    </datalist>
                  </label>
                  <label>
                    표시 버전
                    <input
                      maxLength={200}
                      value={metadata.version_label}
                      onChange={(e) =>
                        setMetadata((m) => ({
                          ...m,
                          version_label: e.target.value,
                        }))
                      }
                    />
                  </label>
                </div>
                <label>
                  모델 설명
                  <textarea
                    maxLength={3000}
                    rows={3}
                    value={metadata.description}
                    onChange={(e) =>
                      setMetadata((m) => ({
                        ...m,
                        description: e.target.value,
                      }))
                    }
                  />
                </label>
                <label>
                  태그 (쉼표로 구분)
                  <input
                    maxLength={1200}
                    value={tagText}
                    onChange={(e) => setTagText(e.target.value)}
                  />
                </label>
                <label>
                  관리 메모
                  <textarea
                    rows={3}
                    maxLength={3000}
                    value={metadata.notes}
                    onChange={(e) =>
                      setMetadata((m) => ({ ...m, notes: e.target.value }))
                    }
                  />
                </label>
                <label>
                  실행 대상 구성
                  <select
                    value={artifact.adapter_id}
                    onChange={(e) => {
                      const a = data?.supported_artifacts.find(
                        (a) => a.adapter_id === e.target.value,
                      );
                      setArtifact({
                        adapter_id: a?.adapter_id || "",
                        revision: a?.revision || "",
                      });
                    }}
                  >
                    <option value="">미지정 · 관리만 (실행 미지원)</option>
                    {data?.supported_artifacts.map((a) => (
                      <option key={a.adapter_id} value={a.adapter_id}>
                        {a.name}
                      </option>
                    ))}
                  </select>
                </label>
                {artifact.adapter_id ? (
                  <p className="registry-path caption">
                    고정 가중치 버전: {artifact.revision}
                    <br />이 앱에서 준비한 지정 모델을 실행합니다. 보관 위치를
                    선택하는 것만으로 파일 검증을 완료하지 않습니다.
                  </p>
                ) : (
                  <label>
                    가중치 버전 메모
                    <input
                      maxLength={200}
                      value={artifact.revision}
                      onChange={(e) =>
                        setArtifact((a) => ({ ...a, revision: e.target.value }))
                      }
                    />
                  </label>
                )}
                {newCandidate ? (
                  <p className="registry-path">
                    선택한 파일 후보: {newCandidate.path}
                  </p>
                ) : null}
                {selected ? (
                  <label className="registry-check">
                    <input
                      type="checkbox"
                      checked={replaceRefs}
                      onChange={(e) => setReplaceRefs(e.target.checked)}
                    />
                    보관 참조를 새 위치로 교체 (현재 검증 해제)
                  </label>
                ) : null}
                <label>
                  로컬 검증 자산 폴더 (선택)
                  <input
                    value={local}
                    onChange={(e) => setLocal(e.target.value)}
                    placeholder="사용자가 지정한 전체 절대 경로"
                    maxLength={32767}
                  />
                  <small>
                    {artifact.adapter_id
                      ? "저장할 때 고정 구성에 명시된 파일만 전량 SHA-256으로 확인합니다. 일치하는 자산이 있어야 이 모델을 실행할 수 있습니다."
                      : "폴더 존재만 관측합니다. 아직 이 모델의 구성·무결성·실행을 검증하지 않습니다."}{" "}
                    복사·다운로드는 시작하지 않습니다.
                  </small>
                </label>
                {selected && !replaceRefs ? (
                  <p className="caption">
                    기존 보관 참조 {selected.references.length}개를 유지하고
                    입력한 새 위치를 추가합니다.
                  </p>
                ) : null}
              </fieldset>
              <div className="registry-actions">
                <button
                  type="submit"
                  className="primary"
                  disabled={busy || !csrf.current}
                >
                  {busy ? "저장 중…" : "모델 정보 저장"}
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => setEditing(false)}
                >
                  편집 닫기
                </button>
              </div>
            </form>
          ) : selected ? (
            <>
              <div className="section-title">
                <h2 ref={heading} tabIndex={-1}>
                  {selected.metadata.name}
                </h2>
                <button onClick={() => edit(selected)} disabled={busy}>
                  정보 편집
                </button>
              </div>
              <span
                className={
                  "badge " +
                  (selected.status === "verified" ? "green" : "neutral")
                }
              >
                {statusLabels[selected.status]}
              </span>
              <p>
                {selected.metadata.description || "아직 모델 설명이 없습니다."}
              </p>
              <dl className="registry-facts">
                <dt>용도</dt>
                <dd>{selected.metadata.type}</dd>
                <dt>표시 버전</dt>
                <dd>{selected.metadata.version_label || "미입력"}</dd>
                <dt>등록일</dt>
                <dd>{new Date(selected.created_at).toLocaleString("ko-KR")}</dd>
                <dt>태그</dt>
                <dd>{selected.metadata.tags.join(" · ") || "없음"}</dd>
                <dt>관리 메모</dt>
                <dd>{selected.metadata.notes || "없음"}</dd>
              </dl>
              <h3>보관 위치 · 구성 관측</h3>
              {selected.references.length ? (
                selected.references.map((r) => (
                  <details key={r.identity}>
                    <summary>
                      {r.account ? "Drive 계정 " + r.account : "로컬 폴더"} ·{" "}
                      {r.components.length}개 구성 참조
                    </summary>
                    <p className="registry-path">{r.path}</p>
                    <p className="caption">
                      {r.artifact_match
                        ? "기록된 지정 구성 파일의 SHA-256 일치"
                        : r.observation_status === "complete"
                          ? "완료된 수집의 관측 정보"
                          : "부분 수집 또는 아직 검증하지 않은 위치"}{" "}
                      · 파일 존재·해시·실행은 별도 확인입니다.
                      {r.checked_at
                        ? " 확인 시각: " +
                          new Date(r.checked_at).toLocaleString("ko-KR")
                        : ""}
                    </p>
                    <ul>
                      {r.components.map((c, i) => (
                        <li key={i}>
                          {c.name} ·{" "}
                          {c.size === null || c.size === undefined
                            ? "크기 미확인"
                            : c.size.toLocaleString() + " bytes"}
                          {c.sha256 ? (
                            <details>
                              <summary>파일 해시</summary>
                              <span className="registry-path">{c.sha256}</span>
                            </details>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                  </details>
                ))
              ) : (
                <p className="caption">등록된 보관 위치가 없습니다.</p>
              )}
              {selected.configuration_reasons.map((r) => (
                <p className="caption" key={r}>
                  {reasons[r] || "구성 상태를 다시 확인하세요."}
                </p>
              ))}
              <h3>현재 구성의 새 실행</h3>
              <dl className="registry-facts">
                <dt>등록 자산 해시</dt>
                <dd>
                  {selected.integrity === "recorded_hash_match"
                    ? "지정 구성과 일치한 기록 있음"
                    : "아직 확인하지 않음"}
                </dd>
                <dt>실행용 파일</dt>
                <dd>
                  {selected.preparation === "recorded_ready"
                    ? "준비 기록과 현재 파일 상태 일치"
                    : "준비 확인 필요"}
                </dd>
                <dt>추론 환경</dt>
                <dd>
                  {selected.runtime === "ready"
                    ? "환경 점검 완료 · 실제 실행과 별도"
                    : "환경 점검 필요"}
                </dd>
                <dt>실제 실행</dt>
                <dd>{statusLabels[selected.execution] || "미확인"}</dd>
              </dl>
              <p className="caption">
                검증 완료는 현재 등록 구성에 연결한 실행 시점의 근거입니다. 파일
                상태가 바뀌거나 구성 세대가 달라지면 현재 검증에 포함하지
                않습니다.
              </p>
              <p className="registry-path caption">
                {selected.artifact.adapter_id || "실행 어댑터 미지정"}
                <br />
                {selected.artifact.revision || "가중치 버전 미지정"}
              </p>
              {selected.artifact.adapter_id && !selected.archived ? (
                <>
                  <label>
                    새 한국어 테스트 입력
                    <textarea
                      rows={3}
                      maxLength={300}
                      value={text}
                      onChange={(e) => setText(e.target.value)}
                      disabled={busy}
                    />
                  </label>
                  <p className="caption">
                    {Array.from(text).length} / 300자 · 과거 결과를 재사용하지
                    않습니다.
                  </p>
                  <div className="registry-actions">
                    <button
                      className="primary"
                      onClick={() => void run()}
                      disabled={
                        busy ||
                        !text.trim() ||
                        selected.configuration_attention ||
                        !csrf.current
                      }
                    >
                      이 모델 새로 실행
                    </button>
                    <button onClick={onPrepare}>모델 준비 확인</button>
                  </div>
                </>
              ) : (
                <p className="caption">
                  관리 정보 등록은 모든 모델에 제공됩니다. 실제 실행은 지정된 두
                  Qwen TTS 구성만 지원합니다.
                </p>
              )}
              <h3>이 모델의 실행 기록</h3>
              {!selected.runs.length ? (
                <p className="caption">
                  등록 이후 연결한 실행이 없습니다. 과거 음성 작업실 기록은
                  자동으로 검증 완료에 포함하지 않습니다.
                </p>
              ) : (
                selected.runs.map(({ run, current_artifact, verified }) => (
                  <article className="registry-run" key={run.id}>
                    <strong>
                      {statusLabels[run.status] || "상태 확인 필요"}{" "}
                      {verified ? <Check size={16} /> : null}
                    </strong>
                    <p className="caption">
                      {current_artifact
                        ? "현재 구성"
                        : "이전 구성 · 현재 검증에 포함하지 않음"}{" "}
                      · {run.id.slice(0, 8)}
                    </p>
                    {run.error ? (
                      <p role="status">
                        {errors[run.error] ||
                          "실행을 완료하지 못했습니다. 모델과 환경 상태를 확인하세요."}
                      </p>
                    ) : null}
                    {![
                      "succeeded",
                      "failed",
                      "cancelled",
                      "interrupted",
                    ].includes(run.status) ? (
                      <button
                        disabled={busy || run.status === "cancelling"}
                        onClick={() => void cancelRun(run.id)}
                      >
                        이 실행 취소
                      </button>
                    ) : null}
                    {run.status === "succeeded" && run.audio_url ? (
                      <>
                        <audio
                          key={run.id}
                          controls
                          preload="metadata"
                          src={run.audio_url}
                          aria-label={run.model.name + " 새 실행 결과"}
                        />
                        <AudioDownload id={run.id} url={run.audio_url}>
                          WAV 저장
                        </AudioDownload>
                        <p className="caption">
                          총 처리 시간 (파일 확인·모델 로딩 포함){" "}
                          {run.metrics?.total_seconds?.toFixed(2) ?? "미수집"}초
                          · PyTorch 최대 할당 GPU{" "}
                          {run.metrics?.peak_gpu_allocated_bytes === undefined
                            ? "미수집"
                            : (
                                run.metrics.peak_gpu_allocated_bytes /
                                1024 ** 3
                              ).toFixed(2) + " GiB"}
                        </p>
                      </>
                    ) : null}
                  </article>
                ))
              )}
              <details>
                <summary>등록 식별자 · 현재 구성 근거</summary>
                <p className="registry-path caption">
                  모델 ID {selected.id}
                  <br />
                  구성 세대 {selected.generation}
                  <br />
                  구성 해시 {selected.fingerprint}
                  <br />
                  편집 버전 {selected.row_version}
                </p>
              </details>
              <button
                className="registry-archive"
                disabled={busy}
                onClick={() => void archiveModel()}
              >
                {selected.archived
                  ? "보관 해제 · 새 검증 필요"
                  : "모델 보관 (원본 보존)"}
              </button>
            </>
          ) : (
            <div className="empty">
              <CircleHelp size={26} />
              <h3>모델을 선택하세요</h3>
              <p>
                설명과 보관 위치, 구성 확인 수준, 이 모델의 새 실행 기록을 함께
                볼 수 있습니다.
              </p>
            </div>
          )}
        </aside>
      </div>
    </section>
  );
}
