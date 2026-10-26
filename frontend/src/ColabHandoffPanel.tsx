import { useRef, useState } from "react";

type RequestDocument = {
  request_id: string; request_sha256: string; created_at: string;
  input: { text: string; bytes: number; sha256: string };
  model: { model_id: string; revision: string; manifest_sha256: string };
  execution: { profile_id: string; limits: Record<string, unknown>; runtime: Record<string, string>; source_sha256: Record<string, string> };
};
type ResultDocument = {
  status: "success" | "stopped" | "failure"; reason?: string;
  response?: { text: string; input_tokens: number; generated_tokens: number; eos_reached: boolean; length_cap_reached: boolean };
  phase: { stage: string }; guard: { status: string; reason: string };
  engine?: { model_sha_verified: boolean; runtime_verified: boolean; generation_calls: number };
};
type Detail = { request: RequestDocument; result: ResultDocument | null };
const base = "/api/colab-handoff";
const reasons: Record<string, string> = {
  approval_required: "Colab 실행 승인이 필요합니다", environment_unavailable: "지정 실행 환경이 준비되지 않았습니다",
  source_mismatch: "실행 코드가 일치하지 않습니다", model_mismatch: "모델 파일이 일치하지 않습니다",
  input_token_limit: "입력 토큰 제한을 초과했습니다", guard_stopped: "자원 감시가 실행을 중단했습니다",
  already_started: "이미 실행한 요청입니다", worker_failed: "생성 작업이 실패했습니다",
  output_invalid: "출력 검증에 실패했습니다", cleanup_failed: "실행 정리가 완료되지 않았습니다",
  result_conflict: "이 요청에 다른 결과가 이미 있습니다. 기존 결과를 보존했습니다.",
  request_not_found: "먼저 이 결과에 연결된 요청을 앱에서 내보내세요.",
};
function explain(error: unknown) {
  const code = error instanceof Error ? error.message : "operation_failed";
  return reasons[code] || `요청을 처리하지 못했습니다. 오류 코드: ${code}`;
}
export function ColabResult({ detail }: { detail: Detail }) {
  const result = detail.result;
  if (!result) return <p className="muted">이 요청의 결과를 기다리고 있습니다.</p>;
  return <article className="registry-run" aria-label="Colab 외부 실행 보고">
    <h3>{result.status === "success" ? "외부 생성 완료 보고" : result.status === "stopped" ? "외부 실행 중단 보고" : "외부 실행 실패 보고"}</h3>
    <p>요청 UUID: {detail.request.request_id}</p>
    <p>외부 실행 보고입니다. 파일 일관성을 확인했으며 로컬 실행은 미검증입니다.</p>
    <p>단계: {result.phase.stage} · 자원 감시: {result.guard.status} ({result.guard.reason})</p>
    {result.status === "success" && result.response ? <>
      <p>엔진: 생성 {result.engine?.generation_calls}회 · 모델 무결성 {result.engine?.model_sha_verified ? "확인 보고" : "미확인"} · 실행 환경 {result.engine?.runtime_verified ? "확인 보고" : "미확인"}</p>
      <h4>생성문</h4><pre>{result.response.text}</pre>
      <p>입력 {result.response.input_tokens}토큰 · 출력 {result.response.generated_tokens}토큰 · {result.response.eos_reached ? "EOS 도달" : result.response.length_cap_reached ? "출력 길이 상한 도달 (32토큰)" : "종료 사유 미확인"}</p>
    </> : <p>{reasons[result.reason || ""] || result.reason}</p>}
  </article>;
}
export function ColabHandoffPanel({ csrf }: { csrf: string }) {
  const [text, setText] = useState("물은 얼면 무엇이 되나요?");
  const [preview, setPreview] = useState<RequestDocument | null>(null);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const version = useRef(0);
  async function api<T>(path: string, raw?: string): Promise<T> {
    const response = await fetch(base + path, raw === undefined ? undefined : {
      method: "POST", headers: { "Content-Type": "application/json", "X-AiManager-CSRF": csrf }, body: raw,
    });
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.error === "string" ? data.error : "invalid_response");
    return data;
  }
  async function review() {
    const current = version.current;
    setBusy(true); setError(""); setNotice(""); setPreview(null);
    try {
      const value = await api<RequestDocument>("/preview", JSON.stringify({ text }));
      if (version.current === current && value.input.text === text) setPreview(value);
    } catch (e) { setError(explain(e)); } finally { setBusy(false); }
  }
  async function exportRequest() {
    if (!preview || preview.input.text !== text) return;
    setBusy(true); setError("");
    try {
      const saved = await api<Detail>("/requests", JSON.stringify(preview));
      if (saved.request.request_sha256 !== preview.request_sha256) throw new Error("request_mismatch");
      setDetail(saved);
      const a = document.createElement("a"); a.href = `${base}/requests/${saved.request.request_id}/download`;
      a.download = `${saved.request.request_id}.request.json`; a.click();
      setNotice("요청을 저장하고 다운로드했습니다. Colab에서 직접 파일을 업로드하세요.");
    } catch (e) { setError(explain(e)); } finally { setBusy(false); }
  }
  async function importFile(file: File | undefined) {
    if (!file) return;
    setError(""); setNotice("");
    if (file.size === 0 || file.size > 65536) { setError("결과 JSON은 1~65,536 bytes여야 합니다."); return; }
    if (!/\.json$/i.test(file.name) || !["", "application/json", "text/plain"].includes(file.type)) { setError("결과 JSON 파일 하나를 선택하세요."); return; }
    setBusy(true);
    try {
      const raw = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(await file.arrayBuffer());
      const value = await api<Detail>("/results", raw);
      setDetail(value); setNotice("저장된 요청과 결과 파일의 일관성을 확인했습니다.");
    } catch (e) { setError(explain(e)); } finally { setBusy(false); }
  }
  return <section className="task-panel registry-panel validation-panel" aria-labelledby="colab-heading">
    <div className="section-title"><div><h2 id="colab-heading">Llama · 무료 Colab 파일 실행</h2>
      <p className="muted">로컬 모델 등록·실행 환경·Drive 로그인 없이 요청과 결과를 파일로 전달합니다.</p></div></div>
    <p>입력 검토는 이 PC의 서버에서 처리합니다. Colab 업로드와 실행은 사용자가 직접 진행합니다.</p>
    {error && <p className="error" role="alert">{error}</p>}
    {notice && <p className="registry-notice" role="status">{notice}</p>}
    <h3>1. 입력과 실행 조건 검토</h3>
    <label htmlFor="colab-input">짧은 비밀 없는 입력 (UTF-8 최대 2,048 bytes)</label>
    <textarea id="colab-input" rows={3} value={text} disabled={busy} onChange={e => { version.current++; setText(e.target.value); setPreview(null); setNotice(""); }} />
    <p className="muted">chat template 포함 64토큰 이하는 Colab에서 확인합니다. greedy · seed 0 · batch 1 · 출력 최대 32토큰</p>
    <button type="button" disabled={busy} onClick={review}>입력·요청 미리보기</button>
    {preview && <article className="registry-run" aria-label="내보내기 전 요청 검토">
      <h4>정확한 입력</h4><pre>{preview.input.text}</pre>
      <p>입력 {preview.input.bytes} bytes · 요청 UUID: {preview.request_id}</p>
      <p>모델: {preview.model.model_id} · revision: {preview.model.revision}</p>
      <p>INT8 실행: {preview.execution.profile_id}</p>
      <pre>요청 SHA-256: {preview.request_sha256}</pre>
      <details><summary>전달할 전체 요청 JSON</summary><pre>{JSON.stringify(preview, null, 2)}</pre></details>
      <h3>2. 검토한 요청 내보내기</h3>
      <p>내보내기를 누르면 전체 요청을 이 작업실에 저장하고 JSON 파일을 다운로드합니다.</p>
      <button type="button" disabled={busy} onClick={exportRequest}>요청 저장·JSON 다운로드</button>
    </article>}
    <h3>3. Colab에서 직접 한 번 실행</h3>
    <a href={`${base}/bundle`} download="Llama_App_Request.ipynb">공개 실행 notebook 다운로드</a>
    <p>현재 모델과 지정 실행 환경이 준비된 무료 T4 VM의 기존 Colab notebook을 계속 사용하세요. 다운로드한 notebook의 코드 셀 두 개를 기존 notebook 끝에 추가하고 요청 JSON을 직접 업로드하세요. 기존 ROOT·WORK와 marker를 보존하고, 새 코드 셀에서 요청과 조건을 검토한 뒤 실행 승인 값을 바꾸어 한 번 실행합니다. 새 runtime을 할당하면 기존 모델과 환경이 이어지지 않습니다. 준비가 안 되면 멈추며 설치·모델 다운로드·자동 재시도는 하지 않습니다.</p>
    <h3>4. 결과 JSON 가져오기</h3>
    <label htmlFor="colab-result-file">Colab에서 다운로드한 결과 (최대 64 KiB)</label>
    <input id="colab-result-file" type="file" accept=".json,application/json" disabled={busy} onChange={e => { const file = e.target.files?.[0]; e.target.value = ""; void importFile(file); }} />
    {busy && <p role="status">요청 처리 중</p>}
    {detail && <><h3>연결된 요청</h3><pre>{detail.request.input.text}</pre><ColabResult detail={detail} /></>}
  </section>;
}
