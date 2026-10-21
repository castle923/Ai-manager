import { useEffect, useRef, useState } from "react";

type Candidate = { id: string; fingerprint: string; name: string; is_new: boolean; local_related: boolean; local_reasons: string[]; entity_kind: string };
type Selection = Candidate & { display_name: string; include_name: boolean };
type Job = { job_id: string; status: string; error_code?: string; cost_state?: string };
type Result = { task: string; stale?: boolean; items: { id: string; name?: string; rank: number; task_fit: "high" | "medium" | "low" | "unknown"; category: string; entity_kind: string; reasons: string[]; evidence?: { id: string; code: string; value: string | number | boolean | null }[] }[] };
type Status = { candidates: Candidate[]; snapshot: string; new_count: number; key_saved: boolean; job: Job | null; latest_result: Result | null };
type Preview = { preview_id: string; approval_hash: string; exact_payload: unknown; count_payload: unknown; disclosure: { provider: string; model: string; endpoints: string[]; count_requests: number; message_requests: number; max_output_tokens: number; payload_bytes: number; input_price_per_million_usd: string; output_price_per_million_usd: string; pricing_checked_at: string; max_usd: string; cost_notice: string; retention_notice: string }; expires_at: string | number };
const endpoint = "/api/claude-recommendations";
const active = (job: Job | null | undefined) => !!job && ["queued", "running", "counting", "sending", "pending"].includes(job.status);
const errors: Record<string, string> = {
  reference_expired: "원본 관찰이 변경됐습니다. 목록을 새로 확인하고 직접 다시 선택하세요.",
  preview_expired: "미리보기가 만료됐습니다. 새 미리보기와 승인이 필요합니다.",
  preview_stale: "승인 대상이 변경됐습니다. 새 미리보기와 승인이 필요합니다.",
  already_consumed: "이미 사용한 1회 승인입니다. 자동 재전송하지 않았습니다.",
  provider_key_required: "API 키가 없습니다. 키 설정에서 사용자가 직접 입력하세요.",
  provider_key_unavailable: "로컬 키를 사용할 수 없습니다. 키 설정을 확인하세요.",
  provider_budget_blocked: "예상 비용이 앱 승인 예산을 초과해 유료 요청을 중단했습니다.",
  provider_cost_unknown: "이전 요청 비용이 불명확해 새 요청을 보류합니다. 비용 예약을 유지합니다.",
  provider_timeout: "응답 시간 제한에 도달했습니다. 이미 전송·청구됐을 수 있으며 자동 재시도하지 않습니다.",
  provider_busy: "다른 분류 요청이 진행 중입니다. 완료 또는 취소 상태를 확인하세요.",
  provider_cancelled: "분류 요청이 취소됐습니다. 이미 전송한 자료와 청구는 철회되지 않을 수 있습니다.",
  provider_result_stale: "분류 중 원본이 변경되어 응답을 현재 결과로 적용하지 않았습니다.",
  provider_refused: "공급자가 분류를 거절했습니다. 로컬 규칙을 계속 사용하세요.",
  provider_output_incomplete: "분류 응답이 불완전하여 적용하지 않았습니다.",
  provider_response_invalid: "응답의 후보·근거·형식을 검증하지 못해 적용하지 않았습니다.",
};
const failure = "요청이 거절되었거나 결과를 확인하지 못했습니다. 자동 재시도하지 않습니다. 로컬 규칙은 계속 사용할 수 있습니다.";
const costStates: Record<string, string> = { reserved: "비용 예약 유지", observed: "응답의 사용량 관측 · 실제 청구와 별도", unknown: "비용 불명 · 예약 유지" };
const states: Record<string, string> = { queued: "대기 중", running: "처리 중", counting: "입력 토큰 확인 중", sending: "분류 요청 중", finished: "분류 응답 확인", cancelled: "취소됨", failed: "처리 실패", expired: "원본 변경 · 만료", cost_unknown: "비용 불명 · 예약 유지" };

// Only fixed, same-origin application endpoints are reachable from this component.
async function request<T>(path: string, csrf: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(endpoint + path, {
    method: body === undefined ? "GET" : "POST",
    credentials: "same-origin",
    signal,
    ...(body === undefined ? {} : { headers: { "Content-Type": "application/json", "X-AiManager-CSRF": csrf }, body: JSON.stringify(body) }),
  });
  if (!response.ok) {
    let safeMessage = failure;
    try {
      const value: unknown = await response.json();
      if (value && typeof value === "object" && "error" in value && typeof value.error === "string") safeMessage = errors[value.error] || failure;
    } catch { /* Never display raw HTTP/provider errors. */ }
    throw new Error(safeMessage);
  }
  return response.json() as Promise<T>;
}

export function ClaudeRecommendationsPanel({ task, csrf }: { task: string; csrf: string }) {
  const [enabled, setEnabled] = useState(false);
  const [status, setStatus] = useState<Status | null>(null);
  const [selections, setSelections] = useState<Selection[]>([]);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [maxUsd, setMaxUsd] = useState("0.01");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [refresh, setRefresh] = useState(0);
  const epoch = useRef(0);
  const operation = useRef(false);
  const ignoredJobs = useRef(new Set<string>());
  const snapshot = useRef<string | null>(null);
  const [, tick] = useState(0);
  useEffect(() => {
    if (!preview) return;
    const timer = setInterval(() => tick(value => value + 1), 1000);
    return () => clearInterval(timer);
  }, [preview]);
  const keyInput = useRef<HTMLInputElement>(null);
  const [keyPresent, setKeyPresent] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    const generation = ++epoch.current;
    snapshot.current = null;
    setStatus(null); setSelections([]); setPreview(null); setConfirmed(false);
    setError(""); setNotice(""); setBusy(false); operation.current = false;
    if (!enabled) return () => controller.abort();
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function load() {
      try {
        const value = await request<Status>(`?task=${encodeURIComponent(task)}`, csrf, undefined, controller.signal);
        if (controller.signal.aborted || generation !== epoch.current) return;
        if (snapshot.current && snapshot.current !== value.snapshot) {
          setSelections([]); setPreview(null); setConfirmed(false);
        }
        snapshot.current = value.snapshot;
        setStatus(value);
        if (active(value.job)) timer = setTimeout(load, 1500);
      } catch {
        if (!controller.signal.aborted && generation === epoch.current) setError("로컬 분류 상태를 확인하지 못했습니다. 자동 재전송은 하지 않습니다.");
      }
    }
    void load();
    return () => { controller.abort(); clearTimeout(timer); ++epoch.current; if (keyInput.current) keyInput.current.value = ""; };
  }, [enabled, task, csrf, refresh]);

  function invalidate() { setPreview(null); setConfirmed(false); setError(""); }
  function edit(id: string, change: Partial<Selection>) {
    invalidate();
    setSelections(rows => rows.map(row => row.id === id ? { ...row, ...change } : row));
  }
  async function mutate<T>(path: string, body: unknown, accept: (value: T) => void) {
    if (operation.current) return;
    operation.current = true; setBusy(true); setError("");
    const generation = epoch.current;
    try {
      const value = await request<T>(path, csrf, body);
      if (generation === epoch.current) accept(value);
    } catch (cause) {
      if (generation === epoch.current) setError(cause instanceof Error && Object.values(errors).includes(cause.message) ? cause.message : failure);
    } finally {
      if (generation === epoch.current) { operation.current = false; setBusy(false); }
    }
  }
  const job = status?.job;
  const working = active(job);
  const result = status?.latest_result;
  const locked = busy || working;
  const fitLabel = { high: "높음", medium: "보통", low: "낮음", unknown: "미확인" };
  const entityLabel: Record<string, string> = { model_candidate: "모델 후보 · 식별 미검증", component: "구성요소 · 모델로 확정하지 않음", adapter: "어댑터 · 독립 실행 미확인", unknown: "종류 미확인" };
  const expiresAt = preview ? (typeof preview.expires_at === "number" ? preview.expires_at : Date.parse(preview.expires_at)) : 0;
  const expired = !!preview && (!Number.isFinite(expiresAt) || Date.now() >= expiresAt);

  return <section className="validation-panel reference-preview" aria-label="Claude 분류·추천">
    <h3>Claude 분류·추천</h3>
    <p>신규 후보의 작업 관련성과 검토 순서를 보조합니다. 기존 로컬 규칙과 실행 선택은 유지됩니다. 실측 품질·무결성·실행 가능 판정은 아닙니다.</p>
    <label className="validation-consent"><input type="checkbox" checked={enabled} disabled={locked} onChange={event => { setEnabled(event.target.checked); setKeyPresent(false); }} />Claude 추천 기능 켜기 · 기본 꺼짐</label>
    {error && <p role="alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {enabled && <>
      <p>추천 출처: 로컬 규칙 · Claude 전송은 아래 미리보기의 1회 승인 후에만 가능합니다.</p>
      {!status ? <p role="status">로컬 후보 상태 확인 중…</p> : <>
        <p>이번 유형의 새 검토 후보 {status.new_count}개 · 선택 {selections.length}/20개</p>
        <button type="button" disabled={locked} onClick={() => setRefresh(value => value + 1)}>로컬 목록 새로고침 · 선택 초기화</button>
        <p>모델 이름에도 개인정보가 있을 수 있습니다. 전송할 표시명을 직접 수정하거나 이름 전송을 끄세요. 경로·계정·파일 ID·원본 파일 내용은 전송 대상에서 제외합니다.</p>
        <fieldset disabled={locked} style={{ minWidth: 0, border: "1px solid #d6e0ed", borderRadius: 8 }}>
          <legend>분류할 신규 후보 직접 선택</legend>
          {!status.candidates.length && <p>이 유형에서 새로 검토할 후보가 없습니다.</p>}
          {status.candidates.map(candidate => {
            const row = selections.find(value => value.id === candidate.id);
            return <div key={candidate.id} style={{ padding: "12px 0", overflowWrap: "anywhere" }}>
              <label className="validation-consent"><input type="checkbox" checked={!!row} disabled={!row && selections.length >= 20} onChange={event => {
                invalidate();
                setSelections(rows => event.target.checked ? (rows.length >= 20 || rows.some(value => value.id === candidate.id) ? rows : [...rows, { ...candidate, display_name: candidate.name, include_name: true }]) : rows.filter(value => value.id !== candidate.id));
              }} />{candidate.name}{candidate.is_new ? " · 신규/변경 검토 대기" : " · 이전 검토 후보"}</label>
              <p>{entityLabel[candidate.entity_kind] || entityLabel.unknown} · 로컬 규칙: {candidate.local_related ? "관련 단서 있음" : "관련성 미확인"}</p>
              <ul>{candidate.local_reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul>
              {row && <>
                <label>전송 표시명<input maxLength={120} value={row.display_name} disabled={!row.include_name} onChange={event => edit(row.id, { display_name: event.target.value })} /></label>
                <label className="validation-consent"><input type="checkbox" checked={row.include_name} onChange={event => edit(row.id, { include_name: event.target.checked })} />이 표시명을 외부 전송에 포함</label>
              </>}
            </div>;
          })}
        </fieldset>
        <label>이번 1회 호출의 앱 승인 예산 (USD)<input inputMode="decimal" value={maxUsd} disabled={locked} onChange={event => { setMaxUsd(event.target.value); invalidate(); }} /></label>
        <button type="button" disabled={locked || !selections.length || !/^\d+(\.\d{1,6})?$/.test(maxUsd) || Number(maxUsd) <= 0} onClick={() => {
          invalidate();
          void mutate<Preview>("/preview", { task, selections: selections.map(({ id, fingerprint, display_name, include_name }) => ({ id, fingerprint, display_name, include_name })), max_usd: maxUsd }, setPreview);
        }}>전송 미리보기 만들기 · 외부 호출 없음</button>
        <details>
          <summary>API 키 설정 · 로컬 DPAPI 보관</summary>
          <p>저장 여부: {status.key_saved ? "저장됨 · 값은 표시하지 않음" : "미저장"}. 직접 입력한 키는 이 PC의 이 작업실에 DPAPI 보관합니다. Google 인증과 별도이며 브라우저 저장소에 보관하지 않습니다.</p>
          <form onSubmit={event => {
            event.preventDefault();
            const apiKey = keyInput.current?.value || "";
            if (!apiKey || locked) return;
            if (keyInput.current) keyInput.current.value = "";
            setKeyPresent(false); invalidate();
            void mutate<{ key_saved: boolean }>("/key", { api_key: apiKey }, value => { setStatus(previous => previous ? { ...previous, key_saved: value.key_saved } : previous); setNotice("키 저장 요청을 처리했습니다. 키 값은 다시 표시하지 않습니다."); });
          }}>
            <label>Anthropic API 키<input ref={keyInput} type="password" autoComplete="off" spellCheck={false} disabled={locked} onChange={event => { setKeyPresent(!!event.target.value); invalidate(); }} /></label>
            <button disabled={locked || !keyPresent} type="submit">입력한 키를 이 PC에 저장</button>
          </form>
        </details>
      </>}
      {preview && <div className="notice">
        <h3>이번 1회 전송 미리보기</h3>
        <p>목적: {task} · Claude Haiku 5.5 · Anthropic · 입력 토큰 확인 1회 + 유료 분류 요청 1회 · 최대 출력 2,048 tokens</p>
        <p>전송 대상: api.anthropic.com/v1/messages/count_tokens 및 /v1/messages. 아래 payload·system 지시·schema와 고지 내용을 확인하세요.</p>
        <p>비용은 추정치이며 앱 예산은 공급자 청구 상한이 아닙니다. 세금·가격 변경·계정 조건은 다를 수 있습니다. 취소해도 이미 전송된 자료나 청구를 철회할 수 없습니다. 응답 불명 시 비용 예약을 유지하고 자동 재시도하지 않습니다.</p>
        <h4>유료 Messages 요청 · 정확한 전송 body · 읽기 전용</h4><pre style={{ maxHeight: 360, overflow: "auto", whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{JSON.stringify(preview.exact_payload, null, 2)}</pre>
        <h4>무료 입력 토큰 확인 요청 · 정확한 전송 body · 읽기 전용</h4><p>무료 count 요청도 외부 전송입니다. 아래 자료를 같은 공급자에게 1회 전송합니다.</p><pre style={{ maxHeight: 360, overflow: "auto", whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{JSON.stringify(preview.count_payload, null, 2)}</pre>
        <h4>가격 확인일·요율·비용 예상·보관 정책</h4>
        <dl><dt>가격 확인일</dt><dd>{preview.disclosure.pricing_checked_at}</dd><dt>100만 tokens당 입력 / 출력</dt><dd>USD {preview.disclosure.input_price_per_million_usd} / {preview.disclosure.output_price_per_million_usd}</dd><dt>이번 앱 승인 예산</dt><dd>USD {preview.disclosure.max_usd} · 청구 강제 상한 아님</dd><dt>정제 payload 크기</dt><dd>{preview.disclosure.payload_bytes} bytes · 토큰 수·확정 청구액 아님</dd><dt>비용 예상의 한계</dt><dd>{preview.disclosure.cost_notice}</dd><dt>공급자 보관·예외</dt><dd>{preview.disclosure.retention_notice}</dd></dl>
        <p>공급자 API 데이터의 일반 보관 기간과 정책 예외를 확인하세요. 계정별 별도 보관 약정이 자동 적용된다고 가정하지 않습니다.</p><pre style={{ maxHeight: 300, overflow: "auto", whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{JSON.stringify(preview.disclosure, null, 2)}</pre>
        <p>선택·표시명·예산·작업 유형·원본이 바뀌면 새 미리보기와 승인이 필요합니다. {expired && "이 미리보기는 만료되었습니다."}</p>
        <label className="validation-consent"><input type="checkbox" checked={confirmed} disabled={locked || expired} onChange={event => setConfirmed(event.target.checked)} />위 정확한 전송 내용·두 endpoint·요청 횟수·예산·보관 정책을 확인했고 이번 1회 전송에 동의합니다.</label>
        <button type="button" disabled={locked || !confirmed || expired || !status?.key_saved} onClick={() => {
          const approved = preview;
          setPreview(null); setConfirmed(false);
          void mutate<{ job_id: string; status: string }>("/run", { preview_id: approved.preview_id, approval_hash: approved.approval_hash, acknowledged: true }, value => { setStatus(previous => previous ? { ...previous, job: { ...value, task } } : previous); setRefresh(value => value + 1); });
        }}>이 미리보기로 1회 전송 승인</button>
        <button type="button" disabled={busy} onClick={invalidate}>미리보기·동의 해제</button>
      </div>}
      {job && <div role="status"><p>취소해도 이미 전송한 자료와 비용은 취소되지 않을 수 있습니다. 공급자에 전송된 자료나 청구를 철회하는 기능은 아닙니다.</p><p>분류 상태: {states[job.status] || "확인이 필요한 상태"}{job.cost_state && ` · ${costStates[job.cost_state] || "비용 상태 확인 필요"}`}</p>{job.error_code && <p>{errors[job.error_code] || failure}</p>}{working && <button type="button" disabled={busy} onClick={() => {
        ignoredJobs.current.add(job.job_id); setPreview(null); setConfirmed(false);
        void mutate<{ status: string }>("/cancel", { job_id: job.job_id }, () => { setStatus(previous => previous ? { ...previous, latest_result: null } : previous); setNotice("취소 요청을 보냈습니다. 이미 전송한 자료와 비용은 취소되지 않을 수 있습니다."); setRefresh(value => value + 1); });
      }}>분류 요청 취소</button>}</div>}
      {!working && result && result.task === task && !ignoredJobs.current.has(job?.job_id || "") && <div>
        <h3>Claude 추정 · 검토 우선순위{result.stale ? " · 이전 결과 만료" : ""}</h3>
        <p>직접 선택한 최대 20개 후보끼리의 상대 검토순위이며 미선택 후보는 순위 밖입니다. 전체 보유 모델의 성능 1위라는 뜻이 아닙니다. 작업 적합도 추정 순서입니다. 실제 모델 품질·추론 결과가 아니며 다운로드·등록·대표 선택·실행은 자동으로 하지 않습니다.</p>
        <ol style={{ maxHeight: "none", overflow: "visible" }}>{[...result.items].sort((a, b) => a.rank - b.rank).map(item => <li key={item.id} style={{ overflowWrap: "anywhere", marginBottom: 16 }}>
          <strong>{item.rank}위 · {item.name || "비식별 후보"} · 작업 적합도 추정 {fitLabel[item.task_fit]}</strong>
          <p>{entityLabel[item.entity_kind] || entityLabel.unknown} · 분류 추정: {item.category}</p>
          <ul>{item.reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul>
          {!!item.evidence?.length && <><p>승인한 관찰 근거 · 실물 식별·완전성 검증과 별도</p><ul>{item.evidence.map(evidence => <li key={evidence.id}>{evidence.code}: {evidence.value === null ? "미확인" : String(evidence.value)} <small>({evidence.id})</small></li>)}</ul></>}
        </li>)}</ol>
      </div>}
    </>}
  </section>;
}
