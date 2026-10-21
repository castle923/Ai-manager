import { useEffect, useRef, useState } from "react";
import { ClaudeRecommendationsPanel } from "./ClaudeRecommendationsPanel";

type Reference = {
  kind: "profile" | "candidate" | "registered";
  id: string;
  fingerprint: string;
  name: string;
  task: string;
  label: string;
  reason?: string;
  reasons?: string[];
  source: string;
  runtime?: string;
  revision?: string;
  manifest_sha256?: string;
  scan_id?: string;
  path?: string;
  family?: string;
  profile_hints?: string[];
  matched_profile_metadata?: boolean;
  resource_checks?: {
    metric: string;
    required_bytes: number;
    observed_bytes: number | null;
    status: string;
  }[];
};
type Choice = Pick<Reference, "kind" | "id" | "fingerprint">;
type Resources = {
  observed_at: string;
  ram_total_bytes: number | null;
  ram_available_bytes: number | null;
  disk_free_bytes: number | null;
  workspace_volume: string;
};
type Overview = {
  task: string;
  task_label: string;
  profiles: Reference[];
  candidates: Reference[];
  registered: Reference[];
  registered_total: number;
  resources: Resources;
  representative: {
    revision: number;
    status: string;
    item: Reference | null;
    fallback: Reference | null;
  };
  explanation: string;
};
type Preview = {
  item: Reference;
  workflow: string[];
  missing_checks: string[];
  mode: "reference";
  execution_allowed: false;
  sampled_generation: false;
};
const tasks = {
  tts: "음성 합성",
  stt: "음성 인식",
  llm: "텍스트 생성",
  image: "이미지 생성",
  tracking: "영상 점 추적",
};
const key = (r: Reference) => `${r.kind}:${r.id}`;
const choice = (r: Reference): Choice => ({
  kind: r.kind,
  id: r.id,
  fingerprint: r.fingerprint,
});
const gib = (v: number | null) =>
  v === null ? "미측정" : `${(v / 1024 ** 3).toFixed(1)} GiB`;
const messages: Record<string, string> = {
  reference_expired:
    "원본 관찰이 바뀌었습니다. 목록을 새로 확인하고 직접 다시 선택하세요.",
  representative_stale:
    "다른 화면에서 대표 선택이 변경됐습니다. 새 상태를 확인하세요.",
  representative_stale_preserved:
    "저장 직전에 대표 설정 파일의 외부 변경을 발견했습니다. 기존 파일을 덮어쓰지 않았습니다. 새 상태를 확인하세요.",
  representative_busy:
    "다른 대표 선택을 저장 중입니다. 현재 선택은 유지했습니다.",
};
async function api<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  const body = await response.json();
  if (!response.ok)
    throw new Error(
      messages[body.error] ||
        "참고 모델 정보를 확인하지 못했습니다. 기존 자료는 보존했습니다.",
    );
  return body;
}

export function WorkshopModelsPanel({
  task,
  csrf,
  onManage,
  onPrepare,
  onCandidate,
}: {
  task: string;
  csrf: string;
  onManage: () => void;
  onPrepare: () => void;
  onCandidate: (item: {
    id: string;
    scan_id: string;
    name: string;
    path: string;
    family: string;
  }) => void;
}) {
  const [currentTask, setCurrentTask] = useState(task || "tts");
  const [data, setData] = useState<Overview | null>(null);
  const [selected, setSelected] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [reload, setReload] = useState(0);
  const [busy, setBusy] = useState(false);
  const epoch = useRef(0);
  useEffect(() => {
    setCurrentTask(task || "tts");
  }, [task]);
  useEffect(() => {
    const controller = new AbortController();
    epoch.current += 1;
    setData(null);
    setPreview(null);
    setSelected("");
    setError("");
    setNotice("");
    api<Overview>(`/api/workshop-models?task=${currentTask}`, {
      signal: controller.signal,
    })
      .then((value) => {
        if (!controller.signal.aborted) setData(value);
      })
      .catch((cause) => {
        if (!controller.signal.aborted) setError(String(cause.message));
      });
    return () => {
      controller.abort();
      epoch.current += 1;
    };
  }, [currentTask, reload]);
  const items = data
    ? [...data.profiles, ...data.registered, ...data.candidates]
    : [];
  const item = items.find((r) => key(r) === selected);
  const representative =
    data?.representative.item || data?.representative.fallback;
  async function inspect(target = item) {
    if (!target || busy) return;
    const requested = target;
    const generation = epoch.current;
    setBusy(true);
    setError("");
    setPreview(null);
    try {
      const query = new URLSearchParams({
        task: currentTask,
        ...choice(requested),
      });
      const value = await api<Preview>(`/api/workshop-models/preview?${query}`);
      if (
        value.mode !== "reference" ||
        value.execution_allowed !== false ||
        value.sampled_generation !== false
      )
        throw new Error("참고용 응답의 범위를 확인하지 못했습니다.");
      if (generation === epoch.current) setPreview(value);
    } catch (cause) {
      if (generation === epoch.current) setError((cause as Error).message);
    } finally {
      if (generation === epoch.current) setBusy(false);
    }
  }
  async function save(clear = false) {
    if (!data || (!clear && !item) || busy || !csrf) return;
    const generation = epoch.current;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const next = await api<Overview>("/api/workshop-models/representative", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-AiManager-CSRF": csrf,
        },
        body: JSON.stringify({
          task: currentTask,
          revision: data.representative.revision,
          choice: clear ? null : choice(item!),
        }),
      });
      if (generation === epoch.current) {
        setData(next);
        setNotice(
          clear
            ? "사용자 대표를 해제했습니다. 기준 모델은 참고용으로 표시합니다."
            : "이 유형의 사용자 대표로 표시합니다. 모델 등록이나 실행 허용은 바뀌지 않습니다.",
        );
      }
    } catch (cause) {
      if (generation === epoch.current) setError((cause as Error).message);
    } finally {
      if (generation === epoch.current) setBusy(false);
    }
  }
  return (
    <section
      className="workshop-models panel"
      aria-label="유형별 대표와 연결된 참고 모델"
    >
      <div className="workshop-reference-heading">
        <div>
          <p className="eyebrow">MODEL REFERENCES · 실행과 구분</p>
          <h2>{data?.task_label || "작업 유형"} 대표와 연결된 모델</h2>
        </div>
        <button
          className="secondary"
          disabled={busy}
          onClick={() => setReload((v) => v + 1)}
        >
          참고 목록 새로 확인
        </button>
      </div>
      {!task ? (
        <label>
          참고할 작업 유형
          <select
            value={currentTask}
            disabled={busy}
            onChange={(e) => setCurrentTask(e.target.value)}
          >
            {Object.entries(tasks).map(([id, label]) => (
              <option key={id} value={id}>
                {label}
              </option>
            ))}
          </select>
        </label>
      ) : null}
      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}
      {notice ? (
        <p className="notice" role="status">
          {notice}
        </p>
      ) : null}
      {!data ? (
        <p role="status">
          현재 작업실의 등록·수집 근거를 읽습니다. 모델을 불러오지 않습니다.
        </p>
      ) : (
        <>
          <p>{data.explanation}</p>
          <div className="workshop-reference-summary">
            <article>
              <span className="badge">
                {data.representative.status === "current"
                  ? "사용자 지정 대표 · 표시 전용"
                  : data.representative.status === "expired"
                    ? "이전 대표 · 원본 변경으로 재선택 필요"
                    : "기준 모델 · 참고용 · 보유 미확인"}
              </span>
              <h3>
                {representative?.name ||
                  "원본이 바뀐 대표를 직접 다시 선택하세요"}
              </h3>
              <p>
                대표는 이 유형의 기준으로 표시할 선택입니다. 실측 성능 1위라는
                뜻이 아닙니다. 파일 다운로드·모델 등록·실행 허용은 각각 별도
                단계입니다.
              </p>
              {data.representative.status !== "not_selected" ? (
                <button
                  className="secondary"
                  disabled={busy || !csrf}
                  onClick={() => void save(true)}
                >
                  사용자 대표 해제
                </button>
              ) : null}
            </article>
            <article>
              <h3>실행 목록에 없는 이유</h3>
              <p className="reference-counts">
                <span>전체 등록 {data.registered_total}개</span>
                <span>이 유형 등록 {data.registered.length}개</span>
                <span>관련 후보 {data.candidates.length}개</span>
              </p>
              <p>
                참고 후보는 등록된 실행 모델이 아닙니다. 아래 기존 실행 선택과
                준비 검사를 유지합니다.
              </p>
              <div className="reference-actions">
                <button className="secondary" onClick={onManage}>
                  모델 관리
                </button>
                <button className="secondary" onClick={onPrepare}>
                  실행 준비
                </button>
              </div>
            </article>
          </div>
          <label className="reference-picker">
            연결된 모델 선택 · 참고용
            <select
              value={selected}
              disabled={busy}
              onChange={(e) => {
                setSelected(e.target.value);
                setPreview(null);
                setError("");
              }}
            >
              <option value="">참고할 모델을 직접 선택하세요</option>
              {[
                ["고정 기준 프로필", data.profiles],
                ["등록한 관리 모델", data.registered],
                ["연결된 Drive 후보 · 모델 식별 미확인", data.candidates],
              ].map(([label, entries]) => (
                <optgroup key={label as string} label={label as string}>
                  {(entries as Reference[]).map((r) => (
                    <option key={key(r)} value={key(r)}>
                      {r.name} ·{" "}
                      {r.kind === "candidate"
                        ? "참고용"
                        : r.kind === "registered"
                          ? "등록"
                          : "보유 미확인"}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </label>
          <div className="reference-actions">
            <button
              className="secondary"
              disabled={!item || busy}
              onClick={() => void inspect()}
            >
              작동 방식과 근거 보기
            </button>
            <button
              className="primary"
              disabled={!item || busy || !csrf}
              onClick={() => void save()}
            >
              선택한 모델을 대표로 표시
            </button>
          </div>
          <div
            className="reference-candidates"
            aria-label="연결된 Drive 참고 후보 목록"
          >
            <h3>이 작업과 관련된 연결 후보</h3>
            <p>
              현재 수집의 이름·구성 단서입니다. 아직 등록되지 않은 후보를 실행
              모델로 넣지 않습니다.
            </p>
            {data.candidates.length ? (
              data.candidates.slice(0, 3).map((candidate) => (
                <article key={key(candidate)}>
                  <div>
                    <strong>{candidate.name}</strong>
                    <p>
                      <span className="badge">참고용</span>{" "}
                      {candidate.matched_profile_metadata
                        ? "고정 프로필의 이름·크기 단서 관찰 · 식별·해시 미확인"
                        : "목적 관련 단서만 관찰 · 지원 프로필 미확인"}
                    </p>
                  </div>
                  <button
                    className="secondary"
                    disabled={busy}
                    onClick={() => {
                      setSelected(key(candidate));
                      void inspect(candidate);
                    }}
                  >
                    후보 근거 보기
                  </button>
                </article>
              ))
            ) : (
              <p>
                현재 허용 범위의 수집에서 이 유형과 관련된 후보를 관찰하지
                못했습니다. 모델이 존재하지 않는다는 뜻은 아닙니다.
              </p>
            )}
            {data.candidates.length > 3 ? (
              <p>나머지 후보도 위 선택 목록에서 확인할 수 있습니다.</p>
            ) : null}
          </div>
          {preview ? (
            <article
              className="reference-preview"
              aria-label="참고용 정보 미리보기"
            >
              <span className="badge">참고용 · 실제 생성 없음</span>
              <h3>{preview.item.name}</h3>
              <p>{preview.item.label}</p>
              <p>{preview.workflow.join(" → ")}</p>
              <p>{preview.item.reason}</p>
              {preview.item.reasons?.map((reason, i) => (
                <p key={i}>{reason}</p>
              ))}
              <p>
                위 흐름은 선택한 작업 유형의 처리 규약 설명이며 이 후보 모델이
                실제 생성한 결과가 아닙니다.
              </p>
              <p>아직 확인해야 할 항목: {preview.missing_checks.join(" · ")}</p>
              <details>
                <summary>원본 근거와 범위</summary>
                <p>
                  출처: {preview.item.source} · 이름 단서와 실제 모델 식별은
                  구분합니다.
                </p>
                {preview.item.revision ? (
                  <p>기준 revision: {preview.item.revision}</p>
                ) : null}
                {preview.item.manifest_sha256 ? (
                  <p>기준 manifest SHA-256: {preview.item.manifest_sha256}</p>
                ) : null}
              </details>
              {preview.item.kind === "candidate" &&
              preview.item.scan_id &&
              preview.item.path &&
              preview.item.family ? (
                <button
                  className="secondary"
                  onClick={() =>
                    onCandidate({
                      id: preview.item.id,
                      scan_id: preview.item.scan_id!,
                      name: preview.item.name,
                      path: preview.item.path!,
                      family: preview.item.family!,
                    })
                  }
                >
                  이 후보의 등록 화면 열기 · 아직 저장 안 함
                </button>
              ) : null}
            </article>
          ) : null}
          <details className="reference-readiness">
            <summary>참고용인 이유 · 현재 준비와 로컬 사양</summary>
            <p>
              측정 시각 {data.resources.observed_at} · RAM 전체{" "}
              {gib(data.resources.ram_total_bytes)}, 여유{" "}
              {gib(data.resources.ram_available_bytes)} · 작업실{" "}
              {data.resources.workspace_volume} 저장 공간 여유{" "}
              {gib(data.resources.disk_free_bytes)}
            </p>
            <p>
              GPU 메모리는 미측정입니다. 부족으로 단정하지 않습니다. 준비 기록과
              현재 관측은 다르며 실행 직전 검사는 아직 수행하지 않았습니다.
            </p>
            {data.profiles.map((profile) => (
              <article key={profile.id}>
                <strong>{profile.name}</strong>
                <p>
                  저장된 환경 준비 기록:{" "}
                  {profile.runtime === "ready"
                    ? "준비 기록 있음 · 실행 성공 아님"
                    : "준비 확인 필요"}{" "}
                  · 현재 가중치·해시는 이 화면에서 검증하지 않습니다.
                </p>
                {profile.resource_checks?.length ? (
                  profile.resource_checks.map((c) => (
                    <p key={c.metric}>
                      {c.metric}: 현재 {gib(c.observed_bytes)} / 기존 실행 규약
                      최소 {gib(c.required_bytes)} ·{" "}
                      {c.status === "unknown"
                        ? "미확인"
                        : c.status === "below_recipe_minimum"
                          ? "이번 관측은 규약 최소보다 부족 · 참고용"
                          : "이번 관측에서 최소값 충족 · 실행 보장 아님"}
                    </p>
                  ))
                ) : (
                  <p>
                    이 프로필의 정량 최소 사양을 이 화면에서 임의로 만들지
                    않습니다. 실제 실행 전 조건을 확인합니다.
                  </p>
                )}
              </article>
            ))}
          </details>
        </>
      )}
      <ClaudeRecommendationsPanel key={`claude-${currentTask}`} task={currentTask} csrf={csrf} />
    </section>
  );
}
