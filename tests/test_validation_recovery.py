"""Fresh synthetic M15 recovery counterexamples; no model or historical output."""
import json
import hashlib
import math
import struct
import wave
from pathlib import Path
import unittest
from unittest.mock import patch

import test_validation_control as control
synthetic_source=control.synthetic_source
from ai_manager.validation_contracts import ContractError
from ai_manager.validation_coordinator import Coordinator
from ai_manager.validation_store import ValidationStore
from ai_manager import validation_recovery as recovery


class RecoveryTests(unittest.TestCase):
    def prepared(self,folder,root):
        store,saved,grant=control.ControlTests().prepared(folder,root,action='run_cpu_probe',probe_seconds=0)
        batch=store.consume(saved['plan_id'],grant['approval_id'])['batch_id']
        return store,saved,batch

    def interrupted(self,store,batch):
        cid=store.status(batch)['cases'][0]['id']
        with store.transaction() as db:
            db.execute("UPDATE batches SET status='interrupted' WHERE id=?",(batch,))
            db.execute("UPDATE cases SET status='interrupted',reason='synthetic_interruption' WHERE id=?",(cid,))
        return cid

    def test_explicit_confirmation_and_new_attempt_same_batch(self):
        with synthetic_source(2) as (folder,root):
            store,saved,batch=self.prepared(folder,root);cid=self.interrupted(store,batch)
            before=store.status(batch)
            with self.assertRaisesRegex(ContractError,'explicit_resume'):recovery.approve(store,batch,saved['plan_sha256'])
            grant=recovery.approve(store,batch,saved['plan_sha256'],confirmed=True)
            result=Coordinator(store).run(batch,resume_approval=grant['resume_approval_id'])
            self.assertEqual(result['batch']['id'],batch)
            self.assertEqual(result['batch']['status'],'control_validated')
            self.assertEqual(next(c for c in result['cases'] if c['id']==cid)['attempt'],2)
            self.assertEqual(result['budget']['expires_ms'],before['budget']['expires_ms'])
            self.assertGreaterEqual(result['batch']['read_bytes'],before['batch']['read_bytes'])
            count=len(result['events'])
            replay=Coordinator(store).run(batch,resume_approval=grant['resume_approval_id'])
            self.assertEqual(len(replay['events']),count)

    def test_unconsumed_pending_preserved_and_terminal_case_not_replayed(self):
        with synthetic_source(2) as (folder,root):
            store,saved,batch=self.prepared(folder,root)
            first,second=store.status(batch)['cases']
            with store.transaction() as db:
                db.execute("UPDATE batches SET status='running' WHERE id=?",(batch,))
                db.execute("UPDATE cases SET status='probe_succeeded' WHERE id=?",(first['id'],))
            result=recovery.recover(store,batch)
            self.assertEqual([c['status'] for c in result['cases']],['probe_succeeded','pending'])
            grant=recovery.approve(store,batch,saved['plan_sha256'],confirmed=True)
            result=Coordinator(store).run(batch,resume_approval=grant['resume_approval_id'])
            running=[json.loads(e['body'])['case_id'] for e in result['events'] if e['kind']=='case_running']
            self.assertEqual(running,[second['id']])

    def test_source_change_and_code_change_refuse_new_grant(self):
        for change in ('source','code'):
            with synthetic_source(1) as (folder,root):
                store,saved,batch=self.prepared(folder,root);self.interrupted(store,batch)
                if change=='source':
                    (root/'model0/config.json').write_text('{"changed":true}')
                    with self.assertRaises(ContractError):recovery.approve(store,batch,saved['plan_sha256'],confirmed=True)
                else:
                    with patch('ai_manager.validation_store.control_code_sha',return_value='f'*64):
                        with self.assertRaisesRegex(ContractError,'code_or_catalog'):recovery.approve(store,batch,saved['plan_sha256'],confirmed=True)
                self.assertEqual(store.status(batch)['batch']['status'],'interrupted')

    def test_original_expiry_never_extended(self):
        with synthetic_source(1) as (folder,root):
            store,saved,batch=self.prepared(folder,root);self.interrupted(store,batch)
            expires=store.plan(saved['plan_id'])['expires_ms']
            store.clock=lambda:expires/1000+1
            with self.assertRaisesRegex(ContractError,'expired'):recovery.approve(store,batch,saved['plan_sha256'],confirmed=True)
            self.assertEqual(store.plan(saved['plan_id'])['expires_ms'],expires)

    def test_ledger_missing_row_rejected_without_budget_reset(self):
        with synthetic_source(1) as (folder,root):
            store,saved,batch=self.prepared(folder,root);cid=self.interrupted(store,batch)
            recovery.reserve_attempt(store,batch,cid,'a'*32,False)
            with store.transaction() as db:db.execute('DELETE FROM case_attempts WHERE batch_id=?',(batch,))
            with self.assertRaisesRegex(ContractError,'ledger_inconsistent'):recovery.approve(store,batch,saved['plan_sha256'],confirmed=True)

    def test_read_reservation_corruption_is_not_zero(self):
        with synthetic_source(1) as (folder,root):
            store,saved,batch=self.prepared(folder,root);self.interrupted(store,batch)
            with store.transaction() as db:db.execute('UPDATE batches SET read_bytes=0 WHERE id=?',(batch,))
            with self.assertRaisesRegex(ContractError,'read_ledger'):recovery.approve(store,batch,saved['plan_sha256'],confirmed=True)

    def test_new_cancel_while_resume_reobserves_is_not_cleared(self):
        with synthetic_source(1) as (folder,root):
            store,saved,batch=self.prepared(folder,root);self.interrupted(store,batch)
            grant=recovery.approve(store,batch,saved['plan_sha256'],confirmed=True)
            original=store.check_current
            def cancel_during(record):
                result=original(record);store.cancel(batch);return result
            with patch.object(store,'check_current',side_effect=cancel_during):
                with self.assertRaisesRegex(ContractError,'cancelled_during_check'):Coordinator(store).run(batch,resume_approval=grant['resume_approval_id'])
            self.assertEqual(store.status(batch)['batch']['cancel'],1)
            with store.connection() as db:self.assertEqual(db.execute('SELECT used FROM resume_grants WHERE id=?',(grant['resume_approval_id'],)).fetchone()[0],0)

    def test_ambiguous_spawn_and_live_job_dispatch_zero(self):
        for state,absent,error in [('spawning',True,'spawn_unresolved'),('owned',False,'still_active'),('owned',None,'unobservable')]:
            with synthetic_source(1) as (folder,root):
                store,saved,batch=self.prepared(folder,root);self.interrupted(store,batch)
                directory=store.home/'model-runs'/batch/('d'*32);directory.mkdir(parents=True)
                marker,value=recovery.spawn_marker(directory,'worker')
                recovery.mark_job(marker,value,state)
                mock=patch.object(recovery,'job_absent',side_effect=ContractError('previous_owner_unobservable')) if absent is None else patch.object(recovery,'job_absent',return_value=absent)
                with mock:
                    with self.assertRaisesRegex(ContractError,error):recovery.approve(store,batch,saved['plan_sha256'],confirmed=True)
                self.assertFalse(any(e['kind']=='case_running' for e in store.status(batch)['events']))

    def test_no_third_attempt_and_wrong_grant_do_not_mutate(self):
        with synthetic_source(1) as (folder,root):
            store,saved,batch=self.prepared(folder,root);cid=self.interrupted(store,batch)
            with store.transaction() as db:db.execute('UPDATE cases SET attempt=2 WHERE id=?',(cid,))
            grant=recovery.approve(store,batch,saved['plan_sha256'],confirmed=True)
            with self.assertRaisesRegex(ContractError,'attempt_budget'):Coordinator(store).run(batch,resume_approval=grant['resume_approval_id'])
            self.assertEqual(store.status(batch)['cases'][0]['status'],'interrupted')
            with self.assertRaisesRegex(ContractError,'scope_mismatch'):Coordinator(store).run(batch,resume_approval='e'*32)
            self.assertEqual(store.status(batch)['batch']['status'],'interrupted')

    def test_checkpoint_pause_preserves_completed_child_and_resumes_pending_only(self):
        with synthetic_source(2) as (folder,root):
            store,saved,batch=self.prepared(folder,root)
            coordinator=Coordinator(store);original=coordinator._case
            first=store.status(batch)['cases'][0]['id']
            def checkpoint(b,c,state,*args,**kwargs):
                original(b,c,state,*args,**kwargs)
                if c==first and state=='probe_succeeded':
                    with store.transaction() as db:store.event(db,b,store._clock(db),'pause_requested',dict(boundary='after_current_case'))
            with patch.object(coordinator,'_case',side_effect=checkpoint):result=coordinator.run(batch)
            self.assertEqual(result['batch']['status'],'interrupted')
            self.assertEqual([c['status'] for c in result['cases']],['probe_succeeded','pending'])
            grant=recovery.approve(store,batch,saved['plan_sha256'],confirmed=True)
            result=Coordinator(store).run(batch,resume_approval=grant['resume_approval_id'])
            self.assertEqual(result['batch']['status'],'control_validated')
            self.assertEqual(sum(e['kind']=='case_running' and json.loads(e['body'])['case_id']==first for e in result['events']),1)

    def test_dispatched_marker_loss_is_not_absence(self):
        with synthetic_source(1) as (folder,root):
            store,saved,batch=self.prepared(folder,root);cid=self.interrupted(store,batch)
            recovery.reserve_attempt(store,batch,cid,'a'*32,False)
            with store.transaction() as db:store.event(db,batch,store._clock(db),'case_running',dict(case_id=cid,attempt=1,run_id='a'*32))
            with self.assertRaisesRegex(ContractError,'marker_missing'):recovery.approve(store,batch,saved['plan_sha256'],confirmed=True)

    def test_completed_receipt_input_output_and_metadata_rechecked(self):
        from ai_manager import validation_models as models
        for changed in (None,'input.txt','output.wav','request.json','result.json','receipt.json'):
            with self.subTest(changed=changed),synthetic_source(1) as (folder,root):
                store,saved,batch=self.prepared(folder,root)
                cid=store.status(batch)['cases'][0]['id'];run='c'*32
                directory=store.home/'model-runs'/batch/run;directory.mkdir(parents=True)
                data=b'fresh M15 synthetic input';(directory/'input.txt').write_bytes(data)
                input_sha=hashlib.sha256(data).hexdigest()
                request=dict(run_id=run,input_sha256=input_sha)
                result=dict(status='generated',run_id=run,input_sha256=input_sha,metrics=dict(loading_seconds=0,inference_seconds=1,peak_gpu_allocated_bytes=0,eos_reached=True))
                for name,value in [('request',request),('result',result)]:(directory/(name+'.json')).write_text(json.dumps(value),'utf8')
                with wave.open(str(directory/'output.wav'),'wb') as stream:
                    stream.setparams((1,2,24000,0,'NONE',''));stream.writeframes(struct.pack('<'+'h'*24000,*[int(1000*math.sin(i/11)) for i in range(24000)]))
                record=store.plan(saved['plan_id']);profile=record['plan']['cases'][0]['profile_id']
                proof=dict(batch_id=batch,case_id=cid,run_id=run,plan_sha256=saved['plan_sha256'],code_sha256=record['plan']['code_sha256'],profile_id=profile,status='succeeded',directory=str(directory),
                    ownership=dict(job_active_processes=0,owned_cleanup_verified=True),lineage=dict(input=dict(sha256=input_sha)),request_sha256=models.digest(directory/'request.json'),result_sha256=models.digest(directory/'result.json'),outputs=models.validate_outputs(profile,directory,request,result,0))
                (directory/'receipt.json').write_text(json.dumps(proof),'utf8')
                with store.transaction() as db:
                    db.execute("UPDATE cases SET status='succeeded' WHERE id=?",(cid,))
                    store.event(db,batch,store._clock(db),'case_succeeded',dict(case_id=cid,attempt=1,run_id=run,receipt_sha256=models.digest(directory/'receipt.json')))
                if changed:
                    path=directory/changed;path.write_bytes(path.read_bytes()+b'changed')
                    with self.assertRaises((ContractError,ValueError)):recovery.receipts(store,batch,record)
                else:self.assertEqual(recovery.receipts(store,batch,record)[cid]['run_id'],run)


if __name__=='__main__':unittest.main()
