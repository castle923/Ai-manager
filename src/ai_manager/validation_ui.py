"""Owned M14 UI service. No client-authored plan, approval promotion or auto resume."""
import json
from pathlib import Path
import threading
import uuid

from .validation_contracts import fail, identifier, object_fields
from .validation_store import ValidationStore, build_plan, packed, DB_NAME, control_code_sha
from .validation_intake import safe_path, metadata_json, observe_local
from .validation_coordinator import Coordinator


class ValidationUI:
    def __init__(self, home, settings=None, auth=None):
        self.app_home = Path(home)
        self.settings, self.auth = settings, auth
        self.home = self.app_home / 'validation'
        self.lock = threading.RLock()
        self.worker = None
        self.coordinator = None
        self.closed = False

    def store(self, initialize=False):
        # A broken existing store is never silently replaced.
        return ValidationStore(self.home, initialize=initialize, reobserver=self.reobserve_drive)

    def scopes(self):
        return dict(drive_scopes=[dict(index=i, account=r['account'], connected=bool(self.auth and self.auth.store.get(r['account']))) for i,r in enumerate((self.settings or {}).get('allowlist',[]))], drive_execution_supported=False)

    def provider(self, index):
        if type(index) is not int: fail('drive_scope_invalid')
        roots=(self.settings or {}).get('allowlist',[])
        if not 0<=index<len(roots): fail('drive_scope_invalid')
        root=roots[index]
        if not self.auth or not self.auth.store.get(root['account']): fail('drive_not_connected_user_login_required')
        from .validation_drive import BoundedSession, LiveDriveIntake
        from .drive import Drive
        import requests
        return LiveDriveIntake(Drive(lambda force_refresh=False:self.auth.access(root['account'],force_refresh=force_refresh),session=BoundedSession(requests.Session())),self.settings,root['account'],root['id'])

    def reobserve_drive(self, previous):
        for i,root in enumerate((self.settings or {}).get('allowlist',[])):
            if root['account']==previous['account'] and root['id']==previous['root_id']:
                return self.provider(i).reobserve(previous)
        fail('drive_root_not_allowlisted')

    def initialize(self):
        with self.lock:
            if (self.home / DB_NAME).exists():
                self.store()
            else:
                self.store(initialize=True)
        return self.history()

    def history(self):
        if not self.home.exists():
            return dict(initialized=False, plans=[])
        store = self.store()
        with store.connection() as db:
            rows = db.execute('SELECT p.id,p.sha,p.created_ms,p.expires_ms,p.invalid,a.id approval_id,a.used,b.id batch_id,b.status FROM plans p LEFT JOIN approvals a ON a.plan_id=p.id LEFT JOIN batches b ON b.plan_id=p.id ORDER BY p.created_ms DESC,p.id LIMIT 100').fetchall()
        return dict(initialized=True, plans=[dict(r) for r in rows], limit=100)

    def create_plan(self, data):
        object_fields(data, ('roots', 'action', 'runtimes', 'wall_seconds', 'source', 'drive_scope'))
        if self.closed: fail('application_closing')
        roots = data['roots']
        if not isinstance(roots, list) or len(roots)>6 or any(not isinstance(p,str) or not p for p in roots):
            fail('explicit_roots_required')
        action = data['action']
        if action not in ('validate_control_plan', 'run_cpu_probe', 'run_models'): fail('action_invalid')
        if not isinstance(data['runtimes'],dict): fail('runtime_spec_invalid')
        self.initialize()
        store = self.store()
        if data['source'] == 'drive':
            if action=='run_models' or roots or data['runtimes']: fail('drive_metadata_only_no_model_dispatch')
            observation=self.provider(data['drive_scope']).observe()
            spec=None
        elif data['source'] != 'local': fail('source_kind_invalid')
        elif action == 'run_models':
            from .validation_models import observe_scopes, make_spec
            observation = observe_scopes(roots)
            spec = make_spec(observation, data['runtimes'], str(self.app_home))
        else:
            if len(roots) != 1 or data['runtimes']: fail('control_scope_invalid')
            observation = observe_local(roots[0], depth_limit=2, read_limit=524288)
            spec = None
        directory = self.home / 'observations'
        directory.mkdir(exist_ok=True)
        safe_path(self.home, 'observations')
        oid = uuid.uuid4().hex
        with (directory / (oid+'.json')).open('x',encoding='utf-8') as stream:
            stream.write(packed(observation))
        result = store.save_plan(build_plan(observation, action=action, wall_seconds=data['wall_seconds'], model_spec=spec))
        return self.detail(result['plan_id'])

    def observe(self, data):
        object_fields(data, ('roots','source','drive_scope'))
        if self.closed: fail('application_closing')
        if data['source']=='drive':
            if data['roots']!=[]: fail('drive_scope_invalid')
            observation=self.provider(data['drive_scope']).observe()
        elif data['source']=='local':
            roots=data['roots']
            if not isinstance(roots,list) or len(roots)!=1 or not isinstance(roots[0],str): fail('explicit_single_root_required')
            observation=observe_local(roots[0],depth_limit=2,read_limit=524288)
        else: fail('source_kind_invalid')
        return dict(complete=observation['complete'],fingerprint=observation['fingerprint'],read_bytes=observation['read_bytes'],
            candidates=[{k:c.get(k) for k in ('candidate_id','profile_id','identity','artifact')} for c in observation['candidates']],
            reasons=[e.get('reason','observation_unknown') for e in observation.get('errors',[])],model_test_performed=False)

    def detail(self, plan_id):
        store = self.store()
        record = store.plan(plan_id)
        plan = record['plan']
        # The local UI is private, but raw source paths, process IDs and event bodies
        # are deliberately excluded. Exact private plan remains in the owned DB.
        with store.connection() as db:
            grant = db.execute('SELECT id,used FROM approvals WHERE plan_id=?',(plan_id,)).fetchone()
            batch = db.execute('SELECT id FROM batches WHERE plan_id=?',(plan_id,)).fetchone()
            previous=db.execute('SELECT id,body FROM plans WHERE id<>? AND created_ms<=? ORDER BY created_ms DESC,id LIMIT 1',(plan_id,record['created_ms'])).fetchone()
        now = store.now()
        result = dict(plan_id=plan_id, plan_sha256=record['sha'], action=plan['action'],
            created_ms=record['created_ms'], expires_ms=record['expires_ms'],
            stale=bool(record['invalid'] or now >= record['expires_ms'] or plan['code_sha256'] != control_code_sha()),
            limits=plan['limits'], code_sha256=plan['code_sha256'], catalog_sha256=plan['catalog_sha256'],
            source_fingerprint=plan['observation']['fingerprint'], observation_complete=plan['observation']['complete'],
            hash_bytes=plan.get('model_spec',{}).get('hash_bytes',0),
            approval=dict(grant) if grant else None, batch_id=batch['id'] if batch else None,
            source_scope=([o['root'] for o in plan['observation']['observations']] if plan['observation']['kind']=='local_model_scopes' else [plan['observation'].get('root','Drive account '+plan['observation'].get('account',''))]),
            runtime_summary=plan.get('model_spec',{}),
            cases=plan['cases'], quality='not_evaluated', model_test_performed=False)
        if previous:
            old=json.loads(previous['body'])
            result['comparison_plan_id']=previous['id']
            result['changes']=[k for k in ('action','limits','code_sha256','catalog_sha256','observation','model_spec') if old.get(k)!=plan.get(k)]
        else: result['changes']=[]
        if batch:
            status = store.status(batch['id'])
            result['status'] = status['batch']['status']
            result['cancel_requested'] = bool(status['batch']['cancel'])
            result['budget'] = status['budget']
            result['budget']['consumed_ms']=status['batch']['consumed_ms']
            result['budget']['full_read_reserved']=status['batch']['read_bytes']
            with store.connection() as db:
                result['attempts']=[dict(r) for r in db.execute('SELECT case_id,attempt,run_id,stamp_ms,model_reserved FROM case_attempts WHERE batch_id=? ORDER BY stamp_ms,case_id,attempt',(batch['id'],))]
                resume=db.execute('SELECT id FROM resume_grants WHERE batch_id=? AND used=0 ORDER BY rowid DESC LIMIT 1',(batch['id'],)).fetchone()
            result['resume_approval_id']=resume['id'] if resume else None
            last_resume=max((e['sequence'] for e in status['events'] if e['kind']=='resume_approval_consumed'),default=0)
            rejected=[json.loads(e['body']).get('reason') for e in status['events'] if e['kind']=='resume_rejected' and e['sequence']>last_resume]
            result['resume_error']=rejected[-1] if rejected else None
            from .validation_recovery import RESUMABLE,RETRY
            result['resumable']=status['batch']['status'] in RESUMABLE and any(r['status']=='pending' or r['status'] in RETRY and r['attempt']<2 for r in status['cases'])
            result['model_test_performed'] = status['model_test_performed']
            latest={}
            dispatch=set()
            run_ids={}
            environment={}
            artifacts={}
            progress=[]
            for event in status['events']:
                body=json.loads(event['body'])
                cid=body.get('case_id')
                if cid and event['kind'].startswith('case_'): latest[cid]=body
                if cid and body.get('run_id'): run_ids[cid]=body['run_id']
                if cid and event['kind']=='model_worker_dispatch': dispatch.add(cid)
                if cid and event['kind']=='model_environment_ready': environment[cid]=body
                if cid and event['kind']=='model_artifact_verified': artifacts[cid]=body
                progress.append(dict(sequence=event['sequence'],stamp_ms=event['stamp_ms'],kind=event['kind'],
                    case_id=cid, reason=body.get('reason'), bytes=body.get('bytes')))
            byid={c['case_id']:c for c in plan['cases']}
            result['cases']=[dict(byid[r['id']], status=r['status'], reason=r['reason'],attempt=r['attempt'],
                run_id=run_ids.get(r['id']),
                receipt_sha256=latest.get(r['id'],{}).get('receipt_sha256'),
                model_test_performed=r['id'] in dispatch,
                output='contract_pass' if r['status']=='succeeded' else 'not_verified',
                quality='not_evaluated') for r in status['cases']]
            for case in result['cases']:
                cid=case['case_id']
                case['environment']='gate_pass' if cid in environment else 'blocked' if case['reason'] in ('runtime_not_designated','environment_probe_failed','environment_not_ready','resource_blocked') else 'not_verified'
                case['environment_summary']={k:v for k,v in environment.get(cid,{}).get('observation',{}).items() if k in ('python','packages','cuda_available','gpu_free_bytes','gpu_total_bytes','ram_available_bytes','disk_free_bytes','cpu_count')}
                case['artifact_verification']='full_sha_pass' if cid in artifacts else 'not_verified'
                case['verified_files']=artifacts.get(cid,{}).get('files',0)
                case['verified_bytes']=artifacts.get(cid,{}).get('bytes',0)
                case['receipt_verified']=False
                if case['status']=='succeeded':
                    try:
                        import hashlib
                        identifier(case['run_id'])
                        receipt=safe_path(self.home,'model-runs/'+batch['id']+'/'+case['run_id']+'/receipt.json')
                        if receipt.stat().st_size>4194304: fail('receipt_size_invalid')
                        raw=receipt.read_bytes()
                        proof=metadata_json(raw,maximum=4194304,node_limit=65536)
                        if hashlib.sha256(raw).hexdigest()!=case['receipt_sha256'] or any(proof.get(k)!=v for k,v in dict(batch_id=batch['id'],case_id=cid,plan_sha256=record['sha'],profile_id=case['profile_id'],code_sha256=plan['code_sha256'],status='succeeded').items()): fail('receipt_changed')
                        case['receipt_verified']=True
                        case['outputs']=[dict(bytes=o.get('bytes'),sha256=o.get('sha256')) for o in proof['outputs']]
                        case['ownership_verified']=proof['ownership'].get('job_active_processes')==0 and proof['ownership'].get('owned_cleanup_verified') is True
                    except (OSError,ValueError,KeyError,TypeError):
                        case['output']='not_verified'
                        case['receipt_error']='receipt_unavailable_or_changed'
            result['summary']={name:sum(c['status']==name for c in result['cases']) for name in ('succeeded','deferred','run_failed','cancelled','timed_out','interrupted')}
            result['events']=progress[-100:]
        else: result['status']='awaiting_dispatch' if grant else 'awaiting_approval'
        return result

    def approve(self, data):
        object_fields(data, ('plan_id','plan_sha256','confirmed','action'))
        store=self.store()
        record=store.plan(data['plan_id'])
        if record['plan']['action'] != data['action']: fail('approval_action_mismatch')
        store.approve(data['plan_id'],data['plan_sha256'],confirmed=data['confirmed'])
        return self.detail(data['plan_id'])

    def start(self, data):
        object_fields(data, ('plan_id','approval_id'))
        with self.lock:
            if self.closed: fail('application_closing')
            if self.worker and self.worker.is_alive():
                record=self.store().plan(data['plan_id'])
                with self.store().connection() as db:
                    replay=db.execute('SELECT id FROM batches WHERE plan_id=? AND approval_id=?',(data['plan_id'],data['approval_id'])).fetchone()
                if replay: return self.detail(data['plan_id'])
                fail('validation_operation_running')
            store=self.store()
            result=store.consume(data['plan_id'],data['approval_id'])
            if not result['created']:
                # Replayed POST observes its original batch and cannot restart it.
                return self.detail(data['plan_id'])
            self.coordinator=Coordinator(store)
            self.worker=threading.Thread(target=self.coordinator.run,args=(result['batch_id'],),daemon=False)
            self.worker.start()
        return self.detail(data['plan_id'])

    def cancel(self, data):
        object_fields(data, ('batch_id',))
        self.store().cancel(data['batch_id'])
        return dict(status='cancel_requested')

    def pause(self,data):
        object_fields(data,('batch_id',))
        store=self.store()
        with store.transaction() as db:
            now=store._clock(db)
            row=db.execute('SELECT status FROM batches WHERE id=?',(data['batch_id'],)).fetchone()
            if row is None or row['status'] not in ('pending','running'):fail('batch_not_active')
            store.event(db,data['batch_id'],now,'pause_requested',dict(boundary='after_current_case'))
        return dict(status='pause_requested')

    def recover(self,data):
        object_fields(data,('plan_id','batch_id'))
        store=self.store()
        if store.status(data['batch_id'])['batch']['plan_id']!=data['plan_id']:fail('batch_plan_mismatch')
        from .validation_recovery import recover
        recover(store,data['batch_id'])
        return self.detail(data['plan_id'])

    def approve_resume(self,data):
        object_fields(data,('plan_id','batch_id','plan_sha256','confirmed'))
        store=self.store()
        if store.status(data['batch_id'])['batch']['plan_id']!=data['plan_id']:fail('batch_plan_mismatch')
        from .validation_recovery import approve
        approve(store,data['batch_id'],data['plan_sha256'],confirmed=data['confirmed'])
        return self.detail(data['plan_id'])

    def resume(self,data):
        object_fields(data,('plan_id','batch_id','resume_approval_id'))
        with self.lock:
            if self.closed:fail('application_closing')
            if self.worker and self.worker.is_alive():fail('validation_operation_running')
            store=self.store()
            if store.status(data['batch_id'])['batch']['plan_id']!=data['plan_id']:fail('batch_plan_mismatch')
            identifier(data['resume_approval_id'])
            with store.connection() as db:grant=db.execute('SELECT batch_id,used FROM resume_grants WHERE id=?',(data['resume_approval_id'],)).fetchone()
            if grant is None or grant['batch_id']!=data['batch_id']:fail('resume_approval_scope_mismatch')
            if grant['used']:return self.detail(data['plan_id'])
            # The coordinator consumes the grant while holding the same OS lock
            # used for recovery and every dispatch; polling never starts work.
            self.coordinator=Coordinator(store)
            coordinator=self.coordinator
            def run():
                from .validation_contracts import ContractError
                try:
                    result=coordinator.run(data['batch_id'],resume_approval=data['resume_approval_id'])
                    if result.get('status')=='coordinator_busy':fail('coordinator_busy')
                except Exception as error:
                    reason=str(error) if isinstance(error,ContractError) else 'resume_operation_failed'
                    with store.transaction() as db:store.event(db,data['batch_id'],store._clock(db),'resume_rejected',dict(reason=reason))
            self.worker=threading.Thread(target=run,daemon=False)
            self.worker.start()
        return self.detail(data['plan_id'])

    def supersede(self, data):
        object_fields(data, ('plan_id','plan_sha256'))
        store=self.store()
        record=store.plan(data['plan_id'])
        if record['sha']!=data['plan_sha256']: fail('approval_plan_mismatch')
        with store.transaction() as db:
            row=db.execute('SELECT status FROM batches WHERE plan_id=?',(data['plan_id'],)).fetchone()
            if row and row['status'] in ('pending','running'): fail('active_batch_cancel_first')
            db.execute('UPDATE plans SET invalid=1 WHERE id=?',(data['plan_id'],))
        # History/old grants remain; check_current refuses this plan forever.
        return self.detail(data['plan_id'])

    def close(self):
        with self.lock:
            self.closed=True
            if self.coordinator: self.coordinator.closed.set()
            worker=self.worker
        if worker: worker.join()  # Existing owned Job cleanup finishes before app exit.
