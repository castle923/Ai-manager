"""M12 private SQLite approval/attempt store. Explicit initialization only."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
import stat
import time
import uuid
from .validation_contracts import fail, integer, identifier, choice, object_fields
from .validation_profiles import catalog
from .validation_intake import observation_sha, reobserve, safe_path

DB_NAME='validation-control.sqlite3'
CODE_FILES=('validation_intake.py','validation_drive.py','validation_store.py','validation_coordinator.py','validation_probe.py',
            'validation_cli.py','validation_contracts.py','validation_profiles.py','execution_slot.py','inference.py',
            'drive.py','auth.py','config.py','security.py')


def packed(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)


def control_code_sha():
    # Bind all shipped Python, lock and manifest bytes, including transitive worker helpers.
    root=Path(__file__).parent
    files=list(root.rglob('*.py'))+list(root.rglob('*.json'))+list(root.rglob('*.lock'))
    files += [root.parents[1]/'requirements-runtime.lock']
    files += list((root/'static').rglob('*'))
    files = [p for p in files if p.is_file()]
    try:return observation_sha({str(p.relative_to(root)) if p.is_relative_to(root) else 'requirements-runtime.lock':hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.is_file()})
    except OSError:fail('control_code_unavailable')


def build_plan(observation,*,action='validate_control_plan',wall_seconds=300,probe_seconds=1,timeout_seconds=10,model_spec=None):
    choice(action,('validate_control_plan','run_cpu_probe','run_models'))
    if action=='run_models':
        from .validation_models import check_spec
        if model_spec is None:fail('model_spec_required')
        check_spec(model_spec,observation)
    elif model_spec is not None:fail('model_authority_forbidden')
    integer(wall_seconds,1,1800);integer(probe_seconds,0,30);integer(timeout_seconds,1,60)
    if timeout_seconds>wall_seconds:fail('timeout_exceeds_plan')
    if observation.get('kind') not in (('local_readonly','local_model_scopes') if action=='run_models' else ('local_readonly','drive_live_readonly')) or not observation.get('complete'):fail('source_not_dispatchable')
    if not observation.get('candidates') or len(observation['candidates'])>6:fail('candidate_count_invalid')
    profiles,cat=catalog();cases=[];tts=None
    for candidate in sorted(observation['candidates'],key=lambda x:(not (x.get('profile_id') or '').startswith('qwen3-tts-'),x['candidate_id'])):
        key=candidate['profile_id']
        case=dict(case_id=uuid.uuid4().hex,candidate_id=candidate['candidate_id'],profile_id=key,
                  identity=candidate['identity'],artifact=candidate['artifact'],depends_on=[])
        if key=='whisper-large-v3-turbo' and tts:case['depends_on']=[tts]
        if key and key.startswith('qwen3-tts-') and tts is None:tts=case['case_id']
        cases.append(case)
    result=dict(schema_version=2,plan_id=uuid.uuid4().hex,action=action,
                observation=observation,catalog_sha256=cat,code_sha256=control_code_sha(),
                limits=dict(wall_seconds=wall_seconds,read_bytes=33554432,max_cases=6,
                            max_queued=3,max_active=1,metadata_network_bytes=33554432 if observation['kind']=='drive_live_readonly' else 0,
                            metadata_requests=1024 if observation['kind']=='drive_live_readonly' else 0,
                            model_download_bytes=0,installations=0,model_runs=len(cases) if action=='run_models' else 0),
                probe=dict(seconds=probe_seconds,timeout_seconds=timeout_seconds),cases=cases,
                model_test_performed=False)
    if model_spec is not None:result['model_spec']=model_spec
    return result


class ValidationStore:
    def __init__(self,home,*,initialize=False,clock=time.time,reobserver=None):
        self.home=Path(home);self.clock=clock;self.reobserver=reobserver
        if not self.home.is_absolute():fail('store_path_invalid')
        if initialize:
            if self.home.exists() and any(self.home.iterdir()):fail('store_target_not_empty')
            self.home.mkdir(parents=True,exist_ok=True)
            safe_path(self.home)
        else:
            safe_path(self.home)
        self.db=self.home/DB_NAME
        if not initialize and not self.db.is_file():fail('store_missing_no_auto_reset')
        safe_path(self.home)
        if self.db.exists():safe_path(self.home,DB_NAME)
        try:
            if initialize:
                # Exclusive file creation makes simultaneous initialization non-destructive.
                with self.db.open('xb'):pass
                with self.connection() as db:
                    db.executescript('''CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
                    CREATE TABLE plans(id TEXT PRIMARY KEY,sha TEXT UNIQUE NOT NULL,body TEXT NOT NULL,created_ms INTEGER NOT NULL,expires_ms INTEGER NOT NULL,read_reserved INTEGER NOT NULL,network_reserved INTEGER NOT NULL,requests_reserved INTEGER NOT NULL,invalid INTEGER NOT NULL DEFAULT 0);
                    CREATE TABLE approvals(id TEXT PRIMARY KEY,plan_id TEXT UNIQUE NOT NULL REFERENCES plans(id),plan_sha TEXT NOT NULL,action TEXT NOT NULL,issued_ms INTEGER NOT NULL,expires_ms INTEGER NOT NULL,used INTEGER NOT NULL DEFAULT 0);
                    CREATE TABLE batches(id TEXT PRIMARY KEY,plan_id TEXT UNIQUE NOT NULL REFERENCES plans(id),approval_id TEXT UNIQUE NOT NULL REFERENCES approvals(id),status TEXT NOT NULL,cancel INTEGER NOT NULL DEFAULT 0,consumed_ms INTEGER NOT NULL DEFAULT 0,read_bytes INTEGER NOT NULL DEFAULT 0,model_test INTEGER NOT NULL DEFAULT 0);
                    CREATE TABLE cases(id TEXT PRIMARY KEY,batch_id TEXT NOT NULL REFERENCES batches(id),position INTEGER NOT NULL,status TEXT NOT NULL,reason TEXT,attempt INTEGER NOT NULL DEFAULT 1);
                    CREATE TABLE events(sequence INTEGER PRIMARY KEY AUTOINCREMENT,batch_id TEXT NOT NULL,stamp_ms INTEGER NOT NULL,kind TEXT NOT NULL,body TEXT NOT NULL);''')
                    db.executemany('INSERT INTO meta VALUES (?,?)',[('schema','2'),('store_id',uuid.uuid4().hex),
                        ('scope',observation_sha(str(self.home))),('last_clock_ms',str(self.now()))])
            with self.transaction() as db:
                values=dict(db.execute('SELECT key,value FROM meta'))
                if values.get('schema')!='2' or values.get('scope')!=observation_sha(str(self.home)):fail('store_scope_mismatch')
                identifier(values['store_id']);self.store_id=values['store_id']
                self._clock(db)
        except (sqlite3.Error,OSError,KeyError,ValueError) as exc:
            from .validation_contracts import ContractError
            if isinstance(exc,ContractError):raise
            fail('store_unavailable_no_auto_reset')

    def now(self):
        value=self.clock()
        if type(value) not in (int,float) or isinstance(value,bool) or not 0<=value<2**40:fail('trusted_clock_invalid')
        return int(value*1000)

    @contextmanager
    def connection(self):
        safe_path(self.home,DB_NAME)
        for suffix in ('-journal','-wal','-shm'):
            try:info=(self.home/(DB_NAME+suffix)).lstat()
            except FileNotFoundError:continue  # SQLite normally removes a committed rollback journal.
            if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400 or not stat.S_ISREG(info.st_mode):fail('store_auxiliary_path_unsafe')
        try:db=sqlite3.connect(self.db.as_uri()+'?mode=rw',uri=True,timeout=10,isolation_level=None)
        except sqlite3.Error:fail('store_unavailable_no_auto_reset')
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON');db.execute('PRAGMA synchronous=FULL')
        try:
            if hasattr(self,'store_id'):
                values=dict(db.execute('SELECT key,value FROM meta'))
                if values.get('store_id')!=self.store_id or values.get('scope')!=observation_sha(str(self.home)):fail('store_scope_mismatch')
            yield db
        finally:db.close()

    @contextmanager
    def transaction(self):
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            try:yield db;db.execute('COMMIT')
            except BaseException:db.execute('ROLLBACK');raise

    def _clock(self,db):
        now=self.now();last=int(db.execute("SELECT value FROM meta WHERE key='last_clock_ms'").fetchone()[0])
        if now<last:fail('trusted_clock_rollback')
        db.execute("UPDATE meta SET value=? WHERE key='last_clock_ms'",(str(now),))
        return now

    def save_plan(self,plan):
        fields=('schema_version','plan_id','action','observation','catalog_sha256','code_sha256','limits','probe','cases','model_test_performed')
        object_fields(plan,fields+('model_spec',) if plan.get('action')=='run_models' else fields)
        if plan.get('schema_version')!=2 or plan.get('code_sha256')!=control_code_sha():fail('plan_code_stale')
        identifier(plan['plan_id']);choice(plan['action'],('validate_control_plan','run_cpu_probe','run_models'))
        if plan['action']=='run_models':
            from .validation_models import check_spec
            check_spec(plan['model_spec'],plan['observation'])
        limits=object_fields(plan['limits'],('wall_seconds','read_bytes','max_cases','max_queued','max_active','metadata_network_bytes','metadata_requests','model_download_bytes','installations','model_runs'))
        integer(limits['wall_seconds'],1,1800);integer(limits['read_bytes'],1,33554432)
        for name,value in [('max_cases',6),('max_queued',3),('max_active',1),('model_download_bytes',0),('installations',0),('model_runs',len(plan['cases']) if plan['action']=='run_models' else 0)]:integer(limits[name],value,value)
        integer(limits['metadata_network_bytes'],0,33554432);integer(limits['metadata_requests'],0,1024)
        probe=object_fields(plan['probe'],('seconds','timeout_seconds'))
        integer(probe['seconds'],0,30);integer(probe['timeout_seconds'],1,min(60,limits['wall_seconds']))
        if plan['model_test_performed'] is not False:fail('model_authority_forbidden')
        observation=plan['observation']
        if observation.get('kind') not in (('local_readonly','local_model_scopes') if plan['action']=='run_models' else ('local_readonly','drive_live_readonly')) or observation.get('complete') is not True:fail('source_not_dispatchable')
        candidates={x['candidate_id']:x for x in observation['candidates']}
        if type(plan['cases']) is not list or not 1<=len(plan['cases'])<=6:fail('case_count_invalid')
        seen={};used=set()
        for case in plan['cases']:
            object_fields(case,('case_id','candidate_id','profile_id','identity','artifact','depends_on'))
            cid=identifier(case['case_id']);candidate=identifier(case['candidate_id'])
            if cid in seen or candidate in used or candidate not in candidates:fail('case_duplicate_or_unknown')
            source=candidates[candidate]
            if any(case[k]!=source[k] for k in ('profile_id','identity','artifact')):fail('case_observation_mismatch')
            if type(case['depends_on']) is not list or len(case['depends_on'])>1:fail('dependency_invalid')
            for dependency in case['depends_on']:
                if dependency not in seen or case['profile_id']!='whisper-large-v3-turbo' or not (seen[dependency]['profile_id'] or '').startswith('qwen3-tts-'):fail('dependency_invalid')
            seen[cid]=case;used.add(candidate)
        if used!=set(candidates):fail('unplanned_candidate')
        encoded=packed(plan);sha=hashlib.sha256(encoded.encode()).hexdigest()
        with self.transaction() as db:
            now=self._clock(db)
            for old in db.execute('SELECT p.body,b.status FROM plans p LEFT JOIN batches b ON b.plan_id=p.id WHERE p.expires_ms>? AND p.invalid=0',(now,)):
                same=json.loads(old['body'])['observation'].get('source_identity')==observation.get('source_identity')
                if same and old['status'] in (None,'pending','running'):fail('duplicate_source_active_plan')
            is_drive=observation['kind']=='drive_live_readonly'
            db.execute('INSERT INTO plans VALUES (?,?,?,?,?,?,?,?,0)',(plan['plan_id'],sha,encoded,now,now+plan['limits']['wall_seconds']*1000,observation['read_bytes'],2097152 if is_drive else 0,64 if is_drive else 0))
        return dict(plan_id=plan['plan_id'],plan_sha256=sha,store_id=self.store_id,expires_ms=now+plan['limits']['wall_seconds']*1000)

    def plan(self,plan_id):
        identifier(plan_id)
        with self.connection() as db:row=db.execute('SELECT * FROM plans WHERE id=?',(plan_id,)).fetchone()
        if row is None:fail('plan_unknown')
        result=dict(row)
        if hashlib.sha256(result['body'].encode()).hexdigest()!=result['sha']:fail('stored_plan_corrupt')
        result['plan']=json.loads(result.pop('body'))
        return result

    def approve(self,plan_id,expected_sha,*,confirmed=False):
        if confirmed is not True:fail('explicit_confirmation_required')
        record=self.plan(plan_id);plan=record['plan']
        if record['sha']!=expected_sha:fail('approval_plan_mismatch')
        with self.connection() as db:
            if db.execute('SELECT id FROM approvals WHERE plan_id=?',(plan_id,)).fetchone():fail('approval_already_issued')
        self.check_current(record)
        with self.transaction() as db:
            now=self._clock(db)
            if now>=record['expires_ms']:fail('approval_expired')
            approval=uuid.uuid4().hex
            try:db.execute('INSERT INTO approvals VALUES (?,?,?,?,?,?,0)',(approval,plan_id,expected_sha,plan['action'],now,record['expires_ms']))
            except sqlite3.IntegrityError:fail('approval_already_issued')
        return dict(approval_id=approval,plan_sha256=expected_sha,action=plan['action'],
                    expires_ms=record['expires_ms'],authority='local_os_user_cli_confirmation',model_test_performed=False)

    def check_current(self,record):
        plan=record['plan']
        if plan['code_sha256']!=control_code_sha() or plan['catalog_sha256']!=catalog()[1]:fail('plan_code_or_catalog_stale')
        if plan['action']=='run_models':
            from .validation_models import check_spec
            check_spec(plan['model_spec'],plan['observation'])
        # Reserve a conservative whole read scope before I/O; failures never refund it.
        reserve=plan['observation']['scope']['read_limit']
        network=2097152 if plan['observation']['kind']=='drive_live_readonly' else 0
        requests=64 if network else 0
        with self.transaction() as db:
            now=self._clock(db)
            row=db.execute('SELECT * FROM plans WHERE id=?',(plan['plan_id'],)).fetchone()
            if row['invalid'] or now>=row['expires_ms']:fail('plan_invalid_or_expired')
            if row['read_reserved']+reserve>plan['limits']['read_bytes']:fail('read_budget_exceeded')
            if row['network_reserved']+network>plan['limits']['metadata_network_bytes'] or row['requests_reserved']+requests>plan['limits']['metadata_requests']:fail('metadata_network_budget_exceeded')
            db.execute('UPDATE plans SET read_reserved=read_reserved+?,network_reserved=network_reserved+?,requests_reserved=requests_reserved+? WHERE id=?',(reserve,network,requests,plan['plan_id']))
            db.execute('UPDATE batches SET read_bytes=read_bytes+? WHERE plan_id=?',(reserve,plan['plan_id']))
        try:
            if plan['observation']['kind']=='drive_live_readonly':
                if self.reobserver is None:fail('live_drive_reobserver_required')
                return self.reobserver(plan['observation'])
            if plan['observation']['kind']=='local_model_scopes':
                from .validation_models import reobserve_scopes
                return reobserve_scopes(plan['observation'])
            return reobserve(plan['observation'])
        except BaseException:
            with self.transaction() as db:db.execute('UPDATE plans SET invalid=1 WHERE id=?',(plan['plan_id'],))
            raise

    def consume(self,plan_id,approval_id):
        identifier(approval_id)
        record=self.plan(plan_id)
        # Reject unknown/wrong grants before source I/O or durable budget reservations.
        with self.connection() as db:
            preliminary=db.execute('SELECT * FROM approvals WHERE id=?',(approval_id,)).fetchone()
            existing=db.execute('SELECT id,approval_id FROM batches WHERE plan_id=?',(plan_id,)).fetchone()
            if preliminary is None or preliminary['plan_id']!=plan_id or preliminary['plan_sha']!=record['sha'] or preliminary['action']!=record['plan']['action']:fail('approval_scope_mismatch')
            if existing:
                if existing['approval_id']!=approval_id:fail('approval_scope_mismatch')
                return dict(batch_id=existing['id'],created=False)
            if preliminary['used'] or self.now()>=preliminary['expires_ms']:fail('approval_used_or_expired')
        self.check_current(record)
        with self.transaction() as db:
            now=self._clock(db)
            existing=db.execute('SELECT id FROM batches WHERE plan_id=?',(plan_id,)).fetchone()
            approval=db.execute('SELECT * FROM approvals WHERE id=?',(approval_id,)).fetchone()
            if approval is None or approval['plan_id']!=plan_id or approval['plan_sha']!=record['sha'] or approval['action']!=record['plan']['action']:fail('approval_scope_mismatch')
            if existing:
                # Idempotent replay returns the original batch, never a second dispatch grant.
                return dict(batch_id=existing['id'],created=False)
            if approval['used'] or now>=approval['expires_ms']:fail('approval_used_or_expired')
            batch=uuid.uuid4().hex
            changed=db.execute('UPDATE approvals SET used=1 WHERE id=? AND used=0',(approval_id,)).rowcount
            if changed!=1:fail('approval_used')
            db.execute('INSERT INTO batches(id,plan_id,approval_id,status,read_bytes) VALUES (?,?,?,?,?)',
                       (batch,plan_id,approval_id,'pending',db.execute('SELECT read_reserved FROM plans WHERE id=?',(plan_id,)).fetchone()[0]))
            for n,case in enumerate(record['plan']['cases']):db.execute('INSERT INTO cases(id,batch_id,position,status) VALUES (?,?,?,?)',(case['case_id'],batch,n,'pending'))
            self.event(db,batch,now,'approval_consumed',dict(action=approval['action']))
        return dict(batch_id=batch,created=True)

    def event(self,db,batch,now,kind,body):
        db.execute('INSERT INTO events(batch_id,stamp_ms,kind,body) VALUES (?,?,?,?)',(batch,now,kind,packed(body)))

    def status(self,batch):
        identifier(batch)
        with self.connection() as db:
            row=db.execute('SELECT * FROM batches WHERE id=?',(batch,)).fetchone()
            if row is None:fail('batch_unknown')
            cases=[dict(r) for r in db.execute('SELECT * FROM cases WHERE batch_id=? ORDER BY position',(batch,))]
            events=[dict(r) for r in db.execute('SELECT * FROM events WHERE batch_id=? ORDER BY sequence',(batch,))]
            budget=db.execute('SELECT created_ms,expires_ms,read_reserved,network_reserved,requests_reserved FROM plans WHERE id=?',(row['plan_id'],)).fetchone()
        return dict(batch=dict(row),cases=cases,events=events,budget=dict(budget),
                    budget_accounting='conservative_reserved_not_exact_transferred_bytes',model_test_performed=bool(row['model_test']))

    def cancel(self,batch):
        identifier(batch)
        with self.transaction() as db:
            now=self._clock(db)
            if db.execute('SELECT id FROM batches WHERE id=?',(batch,)).fetchone() is None:fail('batch_unknown')
            db.execute('UPDATE batches SET cancel=1 WHERE id=?',(batch,))
            self.event(db,batch,now,'cancel_requested',{})
