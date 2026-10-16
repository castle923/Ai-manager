import test from 'node:test';
import assert from 'node:assert/strict';
import { buildDownloadRequest, runSingleAttempt } from '../scripts/download_validation.mjs';
const memoryLedger = () => { const rows = new Map(); return {get:async k=>rows.get(k),put:async(k,v)=>rows.set(k,v)}; };
const authorized = { sessionId:'synthetic-session', authorization:'explicit_download_allowed', policyBlocked:false };
test('one side per call and explicit inner/outer timeout with margin',()=>{
  for(const side of ['A','B']) {
    const request=buildDownloadRequest({side});
    assert.equal(request.timeout_ms,150000);
    assert.match(request.code,/downloadMedia\(\{timeoutMs:120000\}\)/);
    assert.equal((request.code.match(/downloadMedia/g)||[]).length,1);
    assert.ok(request.code.includes(side+' WAV 저장'));
  }
  assert.throws(()=>buildDownloadRequest({side:'A',outerTimeoutMs:30000}),/margin/);
});
test('current blocked default never invokes supplied adapter',async()=>{
  let calls=0;
  assert.deepEqual(await runSingleAttempt({sessionId:'mock',side:'A',ledger:memoryLedger(),invoke:async()=>{calls++;}}),{status:'blocked',attempted:false});
  assert.equal(calls,0);
});
test('timeout is indeterminate and forbids same-side retry and B continuation',async()=>{
  const ledger=memoryLedger(); let calls=0;
  const invoke=async request=>{calls++; assert.equal(request.timeout_ms,150000); throw Error('synthetic outer timeout');};
  const result=await runSingleAttempt({...authorized,side:'A',ledger,invoke});
  assert.equal(result.status,'indeterminate');
  assert.equal((await runSingleAttempt({...authorized,side:'A',ledger,invoke})).status,'stopped');
  assert.equal((await runSingleAttempt({...authorized,side:'B',ledger,invoke})).status,'stopped');
  assert.equal(calls,1);
});
test('persisted in-flight survives interrupted host without re-click',async()=>{
  const ledger=memoryLedger(); await ledger.put('download:synthetic-session',{attempts:{A:{status:'in_flight'}}});
  let calls=0; const result=await runSingleAttempt({...authorized,side:'A',ledger,invoke:async()=>{calls++;}});
  assert.equal(result.status,'stopped'); assert.equal(calls,0);
  assert.equal((await runSingleAttempt({...authorized,side:'B',ledger,invoke:async()=>{calls++;}})).status,'stopped'); assert.equal(calls,0);
});
test('returned path is not a file integrity PASS; A and B use separate calls',async()=>{
  const ledger=memoryLedger(); const requests=[];
  const invoke=async request=>{requests.push(request);return {path:'synthetic.wav'};};
  for(const side of ['A','B']) assert.equal((await runSingleAttempt({...authorized,side,ledger,invoke})).status,'path_returned_unverified');
  assert.equal(requests.length,2);
  assert.equal((await runSingleAttempt({...authorized,side:'A',ledger,invoke})).status,'stopped');
});
test('missing tool result stops session rather than claiming download success',async()=>{
  const result=await runSingleAttempt({...authorized,side:'A',ledger:memoryLedger(),invoke:async()=>({})});
  assert.equal(result.status,'indeterminate');
});
