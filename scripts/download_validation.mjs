// Offline orchestration helper. No browser connection, network call, or automatic CLI execution.
export const INNER_TIMEOUT_MS = 120_000;
export const OUTER_TIMEOUT_MS = 150_000;

export function buildDownloadRequest({ side, tabBinding = "m5tab", innerTimeoutMs = INNER_TIMEOUT_MS, outerTimeoutMs = OUTER_TIMEOUT_MS }) {
  if (!['A', 'B'].includes(side)) throw new Error('one_side_required');
  if (!/^[A-Za-z_$][\w$]*$/.test(tabBinding)) throw new Error('invalid_tab_binding');
  if (!Number.isSafeInteger(innerTimeoutMs) || innerTimeoutMs <= 0 ||
      !Number.isSafeInteger(outerTimeoutMs) || outerTimeoutMs < innerTimeoutMs + 30_000) {
    throw new Error('outer_timeout_requires_30s_margin');
  }
  return {
    timeout_ms: outerTimeoutMs,
    title: `Authorized single ${side} download validation`,
    code: `nodeRepl.write({side:${JSON.stringify(side)},path:await ${tabBinding}.playwright.getByRole('link',{name:${JSON.stringify(side + ' WAV 저장')},exact:true}).downloadMedia({timeoutMs:${innerTimeoutMs}})});`,
  };
}

// invoke is supplied by an authorized host adapter; tests use a fake only.
// ledger.get/put must be durable; put must finish BEFORE invoking any browser action.
// A blocked or uncertain side stops the whole session, including a different side.
export async function runSingleAttempt({ sessionId, side, ledger, invoke, authorization, policyBlocked = true }) {
  if (policyBlocked || authorization !== 'explicit_download_allowed') return { status: 'blocked', attempted: false };
  if (!sessionId) throw new Error('session_id_required');
  const key = `download:${sessionId}`;
  const previous = await ledger.get(key) || { attempts: {} };
  if (previous.stopped || previous.attempts[side] || Object.values(previous.attempts).some(attempt => attempt.status === 'in_flight')) return { status: 'stopped', attempted: false };
  const request = buildDownloadRequest({ side });
  const inFlight = { ...previous, attempts: { ...previous.attempts, [side]: { status: 'in_flight' } } };
  await ledger.put(key, inFlight);
  let result;
  try {
    const reply = await invoke(request);
    result = typeof reply?.path === 'string' && reply.path.length > 0
      ? { status: 'path_returned_unverified', attempted: true, path: reply.path }
      : { status: 'indeterminate', attempted: true, reason: 'missing_download_path' };
  } catch (error) {
    result = { status: 'indeterminate', attempted: true, reason: 'tool_error_or_timeout', error: String(error?.message || error) };
  }
  await ledger.put(key, {
    ...inFlight,
    stopped: result.status === 'indeterminate',
    attempts: { ...inFlight.attempts, [side]: result },
  });
  return result;
}
