"""M15 explicit, one-use same-batch recovery. Never repair or replay silently."""
import hashlib
import json
import os
from pathlib import Path
import uuid

from .validation_contracts import fail, identifier
from .validation_intake import safe_path, metadata_json
from .validation_store import packed
from .inference import FileOwner, regular, digest

RESUMABLE = {'interrupted', 'cancelled', 'run_failed', 'timed_out'}
RETRY = {'interrupted', 'cancelled', 'run_failed', 'timed_out'}


def process_stamp(pid):
    """Read creation identity, distinguishing PID reuse and unobservable owners."""
    if type(pid) is not int or pid<=0:fail('owner_identity_invalid')
    if os.name!='nt':
        try:
            raw=Path('/proc/'+str(pid)+'/stat').read_text()
            return dict(pid=pid,creation=raw.rsplit(')',1)[1].split()[19])
        except FileNotFoundError:return None
        except (OSError,IndexError):fail('owner_identity_unobservable')
    import ctypes
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    kernel.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
    kernel.GetProcessTimes.argtypes=[wintypes.HANDLE]+[ctypes.POINTER(wintypes.FILETIME)]*4
    handle=kernel.OpenProcess(0x1000,False,pid)
    if not handle:
        if ctypes.get_last_error() in (87,1168):return None
        fail('owner_identity_unobservable')
    try:
        code=wintypes.DWORD()
        if not kernel.GetExitCodeProcess(handle,ctypes.byref(code)):fail('owner_identity_unobservable')
        if code.value!=259:return None
        created=wintypes.FILETIME();exit_time=wintypes.FILETIME();kernel_time=wintypes.FILETIME();user=wintypes.FILETIME()
        if not kernel.GetProcessTimes(handle,ctypes.byref(created),ctypes.byref(exit_time),ctypes.byref(kernel_time),ctypes.byref(user)):fail('owner_identity_unobservable')
        return dict(pid=pid,creation=str((created.dwHighDateTime<<32)|created.dwLowDateTime))
    finally:kernel.CloseHandle(handle)


def spawn_marker(directory,log_name):
    nonce=uuid.uuid4().hex
    marker=Path(directory)/(log_name+'.job.json')
    value=dict(nonce=nonce,name='Local\\AiManager-M15-'+nonce,state='spawning')
    _durable_marker(marker,value)
    return marker,value


def mark_job(marker,value,state):
    value=dict(value,state=state)
    _durable_marker(marker,value)


def _durable_marker(path,value):
    temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    with temporary.open('xb') as stream:
        stream.write(packed(value).encode());stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,path)


def initialize(db):
    # Additive tables preserve schema-2 plans, grants, cases, events and DB identity.
    db.execute('CREATE TABLE IF NOT EXISTS resume_grants(id TEXT PRIMARY KEY,batch_id TEXT NOT NULL,plan_sha TEXT NOT NULL,state_sha TEXT NOT NULL,used INTEGER NOT NULL DEFAULT 0)')
    db.execute('CREATE TABLE IF NOT EXISTS case_attempts(batch_id TEXT NOT NULL,case_id TEXT NOT NULL,attempt INTEGER NOT NULL,run_id TEXT NOT NULL UNIQUE,stamp_ms INTEGER NOT NULL,model_reserved INTEGER NOT NULL,PRIMARY KEY(batch_id,case_id,attempt))')


def job_absent(name):
    """Observe the exact named Job. Access/query failure is never absence."""
    if os.name != 'nt': fail('recovery_windows_job_required')
    import ctypes
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenJobObjectW.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.LPCWSTR]
    kernel.OpenJobObjectW.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    kernel.QueryInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD,ctypes.c_void_p]
    handle=kernel.OpenJobObjectW(4,False,name)
    if not handle:
        if ctypes.get_last_error()==2: return True
        fail('previous_owner_unobservable')
    class Accounting(ctypes.Structure):
        _fields_=[(n,ctypes.c_int64) for n in ('user','kernel','period_user','period_kernel')]+[(n,wintypes.DWORD) for n in ('faults','total','active','terminated')]
    try:
        value=Accounting()
        if not kernel.QueryInformationJobObject(handle,1,ctypes.byref(value),ctypes.sizeof(value),None): fail('previous_owner_unobservable')
        return value.active==0
    finally: kernel.CloseHandle(handle)


def ownership(store,batch):
    base=store.home/'model-runs'/batch
    status=store.status(batch)
    with store.connection() as db:attempts=[dict(r) for r in db.execute('SELECT * FROM case_attempts WHERE batch_id=?',(batch,))]
    expected=[]
    for event in status['events']:
        body=json.loads(event['body'])
        if event['kind']=='model_worker_dispatch':expected.append((body['run_id'],'worker.log.job.json'))
        elif event['kind']=='case_running':
            matches=[a for a in attempts if a['case_id']==body['case_id'] and a['attempt']==body.get('attempt',1)]
            if len(matches)!=1:fail('ownership_attempt_missing')
            expected.append((matches[0]['run_id'],None))
    for run_id,name in expected:
        identifier(run_id)
        directory=base/run_id
        if not directory.exists() or not list(directory.glob('*.job.json')) or name and not (directory/name).is_file():fail('ownership_marker_missing')
    if not base.exists(): return
    safe_path(base)
    for marker in base.glob('*/*.job.json'):
        path=safe_path(base,marker.relative_to(base).as_posix())
        value=metadata_json(path.read_bytes(),maximum=8192)
        identifier(value['nonce'])
        if value['name']!='Local\\AiManager-M15-'+value['nonce']: fail('ownership_marker_invalid')
        if value['state'] not in ('owned','drained'): fail('previous_spawn_unresolved')
        if not job_absent(value['name']): fail('previous_worker_still_active')


def receipts(store,batch,record):
    """Load only completed cases from this batch, checking receipt AND output bytes."""
    status=store.status(batch); proofs={}
    cases={c['case_id']:c for c in record['plan']['cases']}
    for row in status['cases']:
        if row['status']!='succeeded': continue
        events=[json.loads(e['body']) for e in status['events'] if e['kind']=='case_succeeded' and json.loads(e['body']).get('case_id')==row['id']]
        if len(events)!=1: fail('completed_receipt_ambiguous')
        event=events[0]; identifier(event['run_id'])
        directory=safe_path(store.home,'model-runs/'+batch+'/'+event['run_id'])
        receipt=safe_path(directory,'receipt.json')
        if receipt.stat().st_size>4194304 or digest(receipt)!=event['receipt_sha256']: fail('completed_receipt_changed')
        proof=metadata_json(receipt.read_bytes(),maximum=4194304,node_limit=65536)
        expected=dict(batch_id=batch,case_id=row['id'],run_id=event['run_id'],plan_sha256=record['sha'],code_sha256=record['plan']['code_sha256'],profile_id=cases[row['id']]['profile_id'],status='succeeded',directory=str(directory))
        if any(proof.get(k)!=v for k,v in expected.items()): fail('completed_receipt_scope_mismatch')
        if proof['ownership'].get('job_active_processes')!=0 or proof['ownership'].get('owned_cleanup_verified') is not True: fail('completed_ownership_unverified')
        for name in ('request','result'):
            if digest(safe_path(directory,name+'.json'))!=proof.get(name+'_sha256'):fail('completed_metadata_changed')
        from .validation_models import validate_outputs
        request=metadata_json(safe_path(directory,'request.json').read_bytes(),maximum=65536)
        result=metadata_json(safe_path(directory,'result.json').read_bytes(),maximum=65536)
        input_name='input.wav' if proof['profile_id']=='whisper-large-v3-turbo' else 'input.mp4' if proof['profile_id']=='tapir' else 'input.txt'
        if digest(safe_path(directory,input_name))!=proof['lineage']['input']['sha256'] or request.get('input_sha256')!=proof['lineage']['input']['sha256']:fail('completed_input_changed')
        if validate_outputs(proof['profile_id'],directory,request,result,0)!=proof['outputs']: fail('completed_output_changed')
        proofs[row['id']]=proof
    return proofs


def state_sha(store,batch):
    value=store.status(batch)
    with store.connection() as db:
        attempts=[dict(r) for r in db.execute('SELECT * FROM case_attempts WHERE batch_id=? ORDER BY case_id,attempt',(batch,))]
    cancel_sequence=max((e['sequence'] for e in value['events'] if e['kind']=='cancel_requested'),default=0)
    return hashlib.sha256(packed(dict(batch=value['batch'],cases=value['cases'],budget=value['budget'],attempts=attempts,cancel_sequence=cancel_sequence)).encode()).hexdigest()


def ledger(store,batch):
    value=store.status(batch)
    with store.connection() as db:
        rows=[dict(r) for r in db.execute('SELECT * FROM case_attempts WHERE batch_id=? ORDER BY case_id,attempt',(batch,))]
    expected=[];hash_bytes=0;run_ids=set()
    for event in value['events']:
        body=json.loads(event['body'])
        if event['kind']=='attempt_reserved':
            expected.append(dict(batch_id=batch,case_id=body['case_id'],attempt=body['attempt'],run_id=body['run_id'],stamp_ms=event['stamp_ms'],model_reserved=int(body['model_reserved'])))
        if event['kind']=='weight_hash_reserved':hash_bytes+=body['bytes']
        if event['kind'] in ('case_running','model_worker_dispatch') and body.get('run_id'):run_ids.add(body['run_id'])
    if sorted(expected,key=lambda r:(r['case_id'],r['attempt']))!=rows or not run_ids<={r['run_id'] for r in rows}:fail('attempt_ledger_inconsistent')
    if any(type(value['batch'][k]) is not int or value['batch'][k]<0 for k in ('consumed_ms','read_bytes')):fail('budget_ledger_invalid')
    if value['batch']['read_bytes']!=value['budget']['read_reserved']+hash_bytes:fail('read_ledger_inconsistent')
    if any(r['model_reserved'] not in (0,1) or not 1<=r['attempt']<=2 for r in rows):fail('attempt_ledger_invalid')
    if any(c['status'] not in {'pending','queued','running','succeeded','probe_succeeded','control_validated','deferred','cancelled','timed_out','interrupted','run_failed'} or not 1<=c['attempt']<=2 for c in value['cases']):fail('case_ledger_invalid')


def recover_locked(store,batch):
    status=store.status(batch)
    if status['batch']['status']=='pending':
        consumed=[json.loads(e['body']) for e in status['events'] if e['kind'] in ('approval_consumed','resume_approval_consumed')]
        if not consumed or not consumed[-1].get('owner'):fail('pending_owner_identity_missing')
        previous=consumed[-1]['owner']
        if process_stamp(previous['pid'])==previous:fail('pending_owner_still_alive')
    ownership(store,batch)
    if status['batch']['status'] in ('pending','running'):
        with store.transaction() as db:
            now=store._clock(db)
            db.execute("UPDATE batches SET status='interrupted',consumed_ms=MAX(consumed_ms,?) WHERE id=?",(now-status['budget']['created_ms'],batch))
            db.execute("UPDATE cases SET status='interrupted',reason='previous_owner_lost' WHERE batch_id=? AND status='running'",(batch,))
            for case in status['cases']:
                if case['status']=='running':store.event(db,batch,now,'case_interrupted',dict(case_id=case['id'],attempt=case['attempt'],reason='previous_owner_lost'))
            db.execute("UPDATE cases SET status='pending',reason=NULL WHERE batch_id=? AND status='queued'",(batch,))
            store.event(db,batch,now,'recovered_interrupted',dict(ownership_observed=True,previous_status=status['batch']['status']))
    return store.status(batch)


def recover(store,batch):
    identifier(batch)
    owner=FileOwner(regular(store.home/'validation-coordinator.lock',store.home))
    if not owner.handle: fail('coordinator_busy')
    try: return recover_locked(store,batch)
    finally: owner.close()


def approve(store,batch,expected_sha,*,confirmed=False):
    if confirmed is not True: fail('explicit_resume_confirmation_required')
    identifier(batch)
    owner=FileOwner(regular(store.home/'validation-coordinator.lock',store.home))
    if not owner.handle: fail('coordinator_busy')
    try:
        status=store.status(batch); record=store.plan(status['batch']['plan_id'])
        if record['sha']!=expected_sha: fail('approval_plan_mismatch')
        if status['batch']['status'] not in RESUMABLE: fail('batch_not_resumable')
        ledger(store,batch)
        ownership(store,batch); receipts(store,batch,record)
        if not any(r['status']=='pending' or r['status'] in RETRY for r in status['cases']): fail('no_resumable_cases')
        store.check_current(record)
        snapshot=state_sha(store,batch)
        with store.transaction() as db:
            store._clock(db)
            old=db.execute('SELECT id,state_sha FROM resume_grants WHERE batch_id=? AND used=0',(batch,)).fetchall()
            for row in old:
                if row['state_sha']==snapshot: return dict(resume_approval_id=row['id'],state_sha256=snapshot)
            db.execute('UPDATE resume_grants SET used=1 WHERE batch_id=? AND used=0',(batch,))
            grant=uuid.uuid4().hex
            db.execute('INSERT INTO resume_grants VALUES (?,?,?,?,0)',(grant,batch,record['sha'],snapshot))
        return dict(resume_approval_id=grant,state_sha256=snapshot)
    finally: owner.close()


def consume_locked(store,batch,grant):
    identifier(grant)
    with store.connection() as db: row=db.execute('SELECT * FROM resume_grants WHERE id=?',(grant,)).fetchone()
    if row is None or row['batch_id']!=batch: fail('resume_approval_scope_mismatch')
    if row['used']: return False
    status=store.status(batch);record=store.plan(status['batch']['plan_id'])
    cancel_sequence=max((e['sequence'] for e in status['events'] if e['kind']=='cancel_requested'),default=0)
    if status['batch']['status'] not in RESUMABLE or row['plan_sha']!=record['sha'] or state_sha(store,batch)!=row['state_sha']: fail('resume_state_changed')
    ledger(store,batch)
    ownership(store,batch);receipts(store,batch,record)
    store.check_current(record)
    with store.transaction() as db:
        now=store._clock(db)
        latest=db.execute("SELECT COALESCE(MAX(sequence),0) FROM events WHERE batch_id=? AND kind='cancel_requested'",(batch,)).fetchone()[0]
        if latest!=cancel_sequence:fail('resume_cancelled_during_check')
        if now>=record['expires_ms']: fail('approval_expired')
        if db.execute('UPDATE resume_grants SET used=1 WHERE id=? AND used=0',(grant,)).rowcount!=1: fail('resume_approval_used')
        for case in status['cases']:
            if case['status'] in RETRY:
                if case['attempt']>=2: fail('attempt_budget_exceeded')
                db.execute("UPDATE cases SET status='pending',reason=NULL,attempt=attempt+1 WHERE id=?",(case['id'],))
        db.execute("UPDATE batches SET status='pending',cancel=0 WHERE id=?",(batch,))
        store.event(db,batch,now,'resume_approval_consumed',dict(approval_id=grant,owner=process_stamp(os.getpid())))
    return True


def reserve_attempt(store,batch,case,run_id,model):
    with store.transaction() as db:
        now=store._clock(db)
        row=db.execute('SELECT attempt FROM cases WHERE id=? AND batch_id=?',(case,batch)).fetchone()
        if row is None or row['attempt']>2: fail('attempt_budget_exceeded')
        plan=store.plan(store.status(batch)['batch']['plan_id'])['plan']
        reserved=db.execute('SELECT COALESCE(SUM(model_reserved),0) FROM case_attempts WHERE batch_id=?',(batch,)).fetchone()[0]
        if model and reserved>=plan['limits']['model_runs']: fail('model_run_budget_exceeded')
        db.execute('INSERT INTO case_attempts VALUES (?,?,?,?,?,?)',(batch,case,row['attempt'],run_id,now,int(model)))
        store.event(db,batch,now,'attempt_reserved',dict(case_id=case,attempt=row['attempt'],run_id=run_id,model_reserved=bool(model)))
