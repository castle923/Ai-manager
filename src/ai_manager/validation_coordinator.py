"""M12 bounded durable control dispatcher. Model adapters remain disabled."""
import json
import os
from pathlib import Path
import subprocess
import threading
import time
from .validation_contracts import fail, identifier
from .validation_intake import safe_path
from .inference import FileOwner,OwnedChild,regular
from . import execution_slot

TERMINAL={'control_validated','probe_succeeded','deferred','cancelled','timed_out','interrupted','run_failed'}


class Coordinator:
    def __init__(self,store):
        self.store=store;self.closed=threading.Event()

    def _check(self,batch,record,start):
        status=self.store.status(batch)['batch']
        if self.closed.is_set() or status['cancel']:fail('cancelled')
        with self.store.transaction() as db:
            now=self.store._clock(db)
            actual=db.execute('SELECT invalid,expires_ms FROM plans WHERE id=?',(record['plan']['plan_id'],)).fetchone()
            elapsed=max(now-record['created_ms'],int((time.monotonic()-start)*1000),status['consumed_ms'])
            db.execute('UPDATE batches SET consumed_ms=MAX(consumed_ms,?) WHERE id=?',(elapsed,batch))
        if actual['invalid']:fail('source_stale')
        if now>=actual['expires_ms'] or elapsed>=record['plan']['limits']['wall_seconds']*1000:fail('timed_out')

    def _case(self,batch,case,status,reason=None,**body):
        with self.store.transaction() as db:
            now=self.store._clock(db)
            old=db.execute('SELECT status FROM cases WHERE id=? AND batch_id=?',(case,batch)).fetchone()
            if old is None:fail('case_unknown')
            if old['status'] in TERMINAL:return
            db.execute('UPDATE cases SET status=?,reason=? WHERE id=? AND batch_id=?',(status,reason,case,batch))
            self.store.event(db,batch,now,'case_'+status,dict(case_id=case,reason=reason,**body))

    def run(self,batch):
        identifier(batch);safe_path(self.store.home)
        initial=self.store.status(batch)
        if initial['batch']['status'] in TERMINAL:return initial
        owner=FileOwner(regular(self.store.home/'validation-coordinator.lock',self.store.home))
        if not owner.handle:return dict(status='coordinator_busy',model_test_performed=False)
        start=time.monotonic();child=None;slot=None;process=None;active=None
        try:
            status=self.store.status(batch)
            if status['batch']['status'] in TERMINAL:return status
            record=self.store.plan(status['batch']['plan_id'])
            # A previous claimed/running attempt without its OS lock is interrupted, never auto-replayed.
            if status['batch']['status']=='running':
                with self.store.transaction() as db:
                    now=self.store._clock(db)
                    db.execute("UPDATE batches SET status='interrupted' WHERE id=?",(batch,))
                    db.execute("UPDATE cases SET status='interrupted',reason='previous_owner_lost' WHERE batch_id=? AND status IN ('pending','queued','running')",(batch,))
                    self.store.event(db,batch,now,'recovered_interrupted',{})
                return self.store.status(batch)
            self._check(batch,record,start)
            with self.store.transaction() as db:
                now=self.store._clock(db)
                db.execute("UPDATE batches SET status='running' WHERE id=? AND status='pending'",(batch,))
                self.store.event(db,batch,now,'coordinator_started',dict(pid=os.getpid(),model_test_performed=False))
            cases=record['plan']['cases'];byid={x['case_id']:x for x in cases}
            while True:
                self._check(batch,record,start)
                rows=self.store.status(batch)['cases']
                pending=[r for r in rows if r['status']=='pending'];queued=[r for r in rows if r['status']=='queued']
                for row in pending[:max(0,3-len(queued))]:
                    self._case(batch,row['id'],'queued');queued.append(row)
                if not queued:break
                row=queued[0];active=row['id'];case=byid[active]
                statuses={r['id']:r['status'] for r in self.store.status(batch)['cases']}
                if any(statuses[d] not in ('probe_succeeded','control_validated') for d in case['depends_on']):
                    self._case(batch,active,'deferred','dependency_blocked');active=None;continue
                if case['identity']!='supported_metadata':
                    self._case(batch,active,'deferred','identity_not_supported');active=None;continue
                self.store.check_current(record);self._check(batch,record,start)
                if record['plan']['action']=='validate_control_plan':
                    self._case(batch,active,'deferred','model_executor_not_implemented');active=None;continue
                slot=execution_slot.acquire(self.store.home,lambda:self._check(batch,record,start),self.closed)
                # Reobserve after waiting for the shared app-home GPU slot and immediately before dispatch.
                self.store.check_current(record);self._check(batch,record,start)
                nonce=active
                script=Path(__file__).with_name('validation_probe.py')
                process=subprocess.Popen([getattr(os.sys,'_base_executable',os.sys.executable),'-I','-B',str(script),nonce,
                    str(record['plan']['probe']['seconds']),str(os.getpid())],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,start_new_session=os.name!='nt',
                    creationflags=(subprocess.CREATE_NO_WINDOW|0x4) if os.name=='nt' else 0,
                    env={k:v for k,v in os.environ.items() if k.upper() in ('SYSTEMROOT','WINDIR','TEMP','TMP','LANG','LC_ALL')})
                child=OwnedChild(process)
                self._case(batch,active,'running',pid=process.pid,nonce=nonce,model_test_performed=False)
                begun=time.monotonic()
                while process.poll() is None:
                    self._check(batch,record,start)
                    if time.monotonic()-begun>=record['plan']['probe']['timeout_seconds']:fail('timed_out')
                    self.closed.wait(.03)
                stdout=process.stdout.read(8193)
                if process.returncode!=0 or len(stdout)>8192:fail('cpu_probe_failed')
                try:events=[json.loads(line) for line in stdout.splitlines()]
                except (ValueError,UnicodeError):fail('cpu_probe_failed')
                if len(events)!=2 or [e.get('event') for e in events]!=['cpu_probe_started','cpu_probe_finished'] or any(e.get('nonce')!=nonce or e.get('pid')!=process.pid or e.get('model_test_performed') is not False for e in events):fail('cpu_probe_failed')
                self._case(batch,active,'probe_succeeded',pid=process.pid,nonce=nonce,exit_code=process.returncode,model_test_performed=False)
                child.close();child=None;process.stdout.close();process=None;slot.close();slot=None;active=None
            with self.store.transaction() as db:
                now=self.store._clock(db)
                db.execute("UPDATE batches SET status='control_validated' WHERE id=?",(batch,))
                self.store.event(db,batch,now,'coordinator_finished',dict(model_test_performed=False))
        except BaseException as exc:
            from .validation_contracts import ContractError
            reason='cancelled' if isinstance(exc,KeyboardInterrupt) else str(exc) if isinstance(exc,ContractError) else 'coordinator_internal_error'
            status=reason if reason in ('cancelled','timed_out') else 'run_failed'
            if process is not None and process.poll() is None:
                if os.name!='nt':
                    import signal
                    try:os.killpg(process.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                else:process.kill()
                process.wait(timeout=5)
            if child:child.close();child=None
            if active:self._case(batch,active,status,reason,owned_child_waited=process is None or process.poll() is not None,
                                 exit_code=process.returncode if process else None)
            with self.store.transaction() as db:
                now=self.store.now()
                db.execute('UPDATE batches SET status=? WHERE id=?',(status,batch))
                db.execute("UPDATE cases SET status=?,reason=? WHERE batch_id=? AND status IN ('pending','queued')",(status,reason,batch))
                self.store.event(db,batch,now,'coordinator_stopped',dict(reason=reason,model_test_performed=False))
        finally:
            if child:child.close()
            if process and process.stdout:process.stdout.close()
            if slot:slot.close()
            owner.close()
        return self.store.status(batch)
