import copy
from contextlib import contextmanager
import hashlib
import json
import os
import multiprocessing
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from ai_manager.validation_contracts import ContractError
from ai_manager.validation_profiles import catalog
from ai_manager import validation_intake as intake
from ai_manager.validation_store import ValidationStore,build_plan,DB_NAME
from ai_manager.validation_coordinator import Coordinator


def race_consume(home,plan,approval,gate,output):
    try:
        gate.wait(10)
        result=ValidationStore(Path(home)).consume(plan,approval)
        output.put(result)
    except Exception as exc:output.put(dict(error=type(exc).__name__))


@contextmanager
def synthetic_source(count=6):
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory)/'source';root.mkdir()
        profiles,cat=catalog();manifests={}
        for n,(key,p) in enumerate(list(profiles.items())[:count]):
            folder=root/('model'+str(n));folder.mkdir()
            raw=json.dumps(dict(model_type=key,synthetic_only=True)).encode()
            (folder/'config.json').write_bytes(raw);(folder/'weight.bin').write_bytes(b'new-synthetic-weight')
            manifests[key]=dict(model_id=key,revision=p['revision'],files=[
                dict(path='config.json',size=len(raw),sha256=hashlib.sha256(raw).hexdigest()),
                dict(path='weight.bin',size=20,sha256=hashlib.sha256(b'new-synthetic-weight').hexdigest())])
        with patch.object(intake,'manifest_table',return_value=(profiles,cat,manifests)):
            yield Path(directory),root


class ControlTests(unittest.TestCase):
    def prepared(self,folder,root,**kwargs):
        store=ValidationStore(folder/'home',initialize=True)
        observation=intake.observe_local(root)
        plan=build_plan(observation,**kwargs)
        saved=store.save_plan(plan)
        approval=store.approve(saved['plan_id'],saved['plan_sha256'],confirmed=True)
        return store,saved,approval

    def test_parser_is_nonexecuting_bounded_and_finite(self):
        for raw in (b'{"x":1,"x":2}',b'{"x":NaN}',b'{"x":1e999}',b'['*40+b'0'+b']'*40,b'pickle'):
            with self.assertRaises(ContractError):intake.metadata_json(raw)
        self.assertEqual(intake.metadata_json(b'{"temperature":0.5}'),{'temperature':.5})

    def test_actual_readonly_discovery_six_synthetic_profiles(self):
        with synthetic_source() as (folder,root):
            obs=intake.observe_local(root)
            self.assertTrue(obs['complete']);self.assertEqual(len(obs['candidates']),6)
            self.assertTrue(all(c['identity']=='supported_metadata' for c in obs['candidates']))
            self.assertTrue(all('unverified' in c['artifact'] or 'mismatch' in c['artifact'] for c in obs['candidates']))
            self.assertEqual(intake.reobserve(obs)['fingerprint'],obs['fingerprint'])

    def test_same_config_different_weight_never_integrity_pass(self):
        with synthetic_source(1) as (_,root):
            before=intake.observe_local(root)
            weight=root/'model0/weight.bin';raw=weight.read_bytes();weight.write_bytes(b'x'*len(raw))
            after=intake.observe_local(root)
            self.assertEqual(after['candidates'][0]['identity'],'supported_metadata')
            self.assertNotEqual(after['candidates'][0]['artifact'],'matched')
            self.assertFalse(after['model_test_performed'])
            with self.assertRaisesRegex(ContractError,'source_stale'):intake.reobserve(before)

    def test_hidden_reparse_budget_and_absence_not_deletion(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'.hidden').mkdir();(root/'.hidden/evil.py').write_text('raise RuntimeError')
            obs=intake.observe_local(root)
            self.assertIn('.hidden',obs['excluded']);self.assertEqual(obs['candidates'],[])
            with patch.dict(intake.POLICY,max_entries=1):
                (root/'a').write_text('x');(root/'b').write_text('x')
                obs=intake.observe_local(root)
                self.assertFalse(obs['complete']);self.assertEqual(obs['errors'][0]['reason'],'scan_entry_limit')

    def test_plan_approval_explicit_confirmation_and_source_stale(self):
        with synthetic_source(1) as (folder,root):
            store=ValidationStore(folder/'home',initialize=True)
            plan=build_plan(intake.observe_local(root));saved=store.save_plan(plan)
            with self.assertRaisesRegex(ContractError,'confirmation'):store.approve(saved['plan_id'],saved['plan_sha256'])
            approval=store.approve(saved['plan_id'],saved['plan_sha256'],confirmed=True)
            (root/'model0/config.json').write_text('{"different":true}')
            with self.assertRaisesRegex(ContractError,'source_stale'):store.consume(saved['plan_id'],approval['approval_id'])

    def test_unknown_approval_has_no_read_or_budget_side_effect(self):
        with synthetic_source(1) as (folder,root):
            store=ValidationStore(folder/'home',initialize=True);saved=store.save_plan(build_plan(intake.observe_local(root)))
            before=store.plan(saved['plan_id'])['read_reserved']
            with patch('ai_manager.validation_store.reobserve',side_effect=AssertionError('must_not_read')):
                with self.assertRaisesRegex(ContractError,'approval_scope_mismatch'):store.consume(saved['plan_id'],'f'*32)
            self.assertEqual(before,store.plan(saved['plan_id'])['read_reserved'])

    def test_one_use_durable_idempotency(self):
        with synthetic_source(1) as (folder,root):
            store,saved,approval=self.prepared(folder,root)
            first=store.consume(saved['plan_id'],approval['approval_id'])
            second=ValidationStore(store.home).consume(saved['plan_id'],approval['approval_id'])
            self.assertTrue(first['created']);self.assertFalse(second['created']);self.assertEqual(first['batch_id'],second['batch_id'])
            with self.assertRaisesRegex(ContractError,'already_issued'):store.approve(saved['plan_id'],saved['plan_sha256'],confirmed=True)

    def test_real_six_child_dispatch_bounded_sequential_and_replay(self):
        with synthetic_source() as (folder,root):
            store,saved,approval=self.prepared(folder,root,action='run_cpu_probe',probe_seconds=0)
            batch=store.consume(saved['plan_id'],approval['approval_id'])['batch_id']
            result=Coordinator(store).run(batch)
            self.assertEqual(result['batch']['status'],'control_validated',result)
            self.assertEqual([x['status'] for x in result['cases']],['probe_succeeded']*6)
            events=[(e['kind'],json.loads(e['body'])) for e in result['events']]
            running=0;maximum=0;starts=0;queued=0;maxqueued=0
            for kind,body in events:
                if kind=='case_queued':queued+=1;maxqueued=max(maxqueued,queued)
                if kind=='case_running':running+=1;starts+=1;queued-=1;maximum=max(maximum,running)
                if kind=='case_probe_succeeded':running-=1
            self.assertEqual(starts,6);self.assertEqual(maximum,1);self.assertLessEqual(maxqueued,3)
            count=len(result['events']);again=Coordinator(ValidationStore(store.home)).run(batch)
            self.assertEqual(len(again['events']),count);self.assertFalse(again['model_test_performed'])

    def test_model_adapter_not_implemented_no_child(self):
        with synthetic_source(1) as (folder,root):
            store,saved,approval=self.prepared(folder,root)
            batch=store.consume(saved['plan_id'],approval['approval_id'])['batch_id']
            with patch('subprocess.Popen',side_effect=AssertionError('no_model_child')):
                result=Coordinator(store).run(batch)
            self.assertEqual(result['cases'][0]['reason'],'model_executor_not_implemented')

    def test_cancel_real_child_stops_later_dispatch(self):
        with synthetic_source(2) as (folder,root):
            store,saved,approval=self.prepared(folder,root,action='run_cpu_probe',probe_seconds=5)
            batch=store.consume(saved['plan_id'],approval['approval_id'])['batch_id']
            thread=threading.Thread(target=lambda:Coordinator(store).run(batch));thread.start()
            try:
                deadline=time.monotonic()+10
                while time.monotonic()<deadline and not any(r['status']=='running' for r in store.status(batch)['cases']):time.sleep(.02)
                store.cancel(batch)
            finally:
                store.cancel(batch);thread.join(10)
            self.assertFalse(thread.is_alive())
            result=store.status(batch)
            self.assertEqual(result['batch']['status'],'cancelled')
            self.assertEqual(sum(e['kind']=='case_running' for e in result['events']),1)

    def test_timeout_real_child(self):
        with synthetic_source(1) as (folder,root):
            store,saved,approval=self.prepared(folder,root,action='run_cpu_probe',probe_seconds=3,timeout_seconds=1)
            batch=store.consume(saved['plan_id'],approval['approval_id'])['batch_id']
            self.assertEqual(Coordinator(store).run(batch)['batch']['status'],'timed_out')

    def test_missing_corrupt_or_moved_store_never_auto_reset(self):
        with tempfile.TemporaryDirectory() as directory:
            home=Path(directory)/'home'
            with self.assertRaises(ContractError):ValidationStore(home)
            home.mkdir();(home/DB_NAME).write_bytes(b'not-sqlite')
            with self.assertRaises(ContractError):ValidationStore(home)
            self.assertEqual((home/DB_NAME).read_bytes(),b'not-sqlite')

    def test_corrupt_store_initialization_closes_connection_before_cleanup(self):
        connect=sqlite3.connect
        connections=[]
        class TrackedConnection(sqlite3.Connection):
            closed=False
            def close(self):
                self.closed=True
                super().close()
        def tracked(*args,**kwargs):
            db=connect(*args,**kwargs,factory=TrackedConnection)
            connections.append(db)
            return db
        with tempfile.TemporaryDirectory() as directory:
            home=Path(directory);database=home/DB_NAME
            database.write_bytes(b'new synthetic corrupt database')
            try:
                with patch('ai_manager.validation_store.sqlite3.connect',side_effect=tracked):
                    with self.assertRaisesRegex(ContractError,'store_unavailable_no_auto_reset'):
                        ValidationStore(home)
                self.assertEqual(database.read_bytes(),b'new synthetic corrupt database')
                self.assertEqual(len(connections),1)
                self.assertTrue(connections[0].closed)
            finally:
                for db in connections:db.close()

    def test_multiprocess_consume_exactly_one_transaction(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);root=folder/'source';root.mkdir()
            (root/'config.json').write_text('{"model_type":"unsupported_new_fixture"}')
            store,saved,approval=self.prepared(folder,root)
            context=multiprocessing.get_context('spawn');gate=context.Event();output=context.Queue()
            processes=[context.Process(target=race_consume,args=(str(store.home),saved['plan_id'],approval['approval_id'],gate,output)) for _ in range(2)]
            for p in processes:p.start()
            gate.set();results=[output.get(timeout=20) for _ in processes]
            for p in processes:p.join(20);self.assertEqual(p.exitcode,0)
            self.assertEqual(sum(r.get('created',False) for r in results),1,results)
            self.assertEqual(len({r.get('batch_id') for r in results}),1)

    def test_clock_rollback_expiry_and_reservations_persist(self):
        with synthetic_source(1) as (folder,root):
            now=[1800000000]
            store=ValidationStore(folder/'home',initialize=True,clock=lambda:now[0])
            saved=store.save_plan(build_plan(intake.observe_local(root),wall_seconds=10))
            store.approve(saved['plan_id'],saved['plan_sha256'],confirmed=True)
            read=store.plan(saved['plan_id'])['read_reserved']
            reopened=ValidationStore(store.home,clock=lambda:now[0])
            self.assertEqual(reopened.plan(saved['plan_id'])['read_reserved'],read)
            now[0]-=1
            with self.assertRaisesRegex(ContractError,'clock_rollback'):ValidationStore(store.home,clock=lambda:now[0])
            now[0]+=12
            with self.assertRaisesRegex(ContractError,'expired'):store.check_current(store.plan(saved['plan_id']))

    def test_observation_tampering_and_manifest_second_read(self):
        with synthetic_source(1) as (_,root):
            obs=intake.observe_local(root);obs['candidates'][0]['profile_id']='tapir'
            with self.assertRaisesRegex(ContractError,'observation_tampered'):intake.reobserve(obs)
        with patch('ai_manager.validation_intake.catalog',return_value=catalog()):
            with patch.object(Path,'read_bytes',return_value=b'{"revision":"fake"}'):
                with self.assertRaisesRegex(ContractError,'catalog_manifest_changed'):intake.manifest_table()

    def test_checkpoint_name_size_is_weak_not_supported(self):
        manifest={'tapir':dict(revision='f'*40,files=[dict(path='checkpoint.pt',size=3,sha256='a'*64)])}
        result=intake.identify([dict(path='checkpoint.pt',bytes=3)],{},manifest)
        self.assertEqual(result['identity'],'unknown');self.assertEqual(result['weak_hints'][0]['profile_id'],'tapir')

    def test_moved_database_scope_and_claimed_crash_fail_closed(self):
        import shutil
        with synthetic_source(1) as (folder,root):
            store,saved,approval=self.prepared(folder,root)
            batch=store.consume(saved['plan_id'],approval['approval_id'])['batch_id']
            with store.transaction() as db:db.execute("UPDATE batches SET status='running' WHERE id=?",(batch,))
            result=Coordinator(ValidationStore(store.home)).run(batch)
            self.assertEqual(result['batch']['status'],'interrupted')
            self.assertFalse(any(e['kind']=='case_running' for e in result['events']))
            moved=folder/'moved';moved.mkdir();shutil.copyfile(store.db,moved/DB_NAME)
            with self.assertRaisesRegex(ContractError,'scope_mismatch'):ValidationStore(moved)

    def test_recovery_keeps_all_terminal_failures(self):
        for terminal in ('run_failed','cancelled','timed_out','interrupted'):
            with synthetic_source(2) as (folder,root):
                store,saved,approval=self.prepared(folder,root)
                batch=store.consume(saved['plan_id'],approval['approval_id'])['batch_id']
                first=store.status(batch)['cases'][0]['id']
                with store.transaction() as db:
                    db.execute("UPDATE batches SET status='running' WHERE id=?",(batch,))
                    db.execute('UPDATE cases SET status=?,reason=? WHERE id=?',(terminal,'original_failure',first))
                result=Coordinator(store).run(batch)
                self.assertEqual(result['cases'][0]['status'],terminal)
                self.assertEqual(result['cases'][0]['reason'],'original_failure')

    def test_unknown_batch_has_no_db_events_or_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            store=ValidationStore(Path(directory)/'home',initialize=True)
            with self.assertRaisesRegex(ContractError,'batch_unknown'):Coordinator(store).run('f'*32)
            self.assertFalse((store.home/'validation-coordinator.lock').exists())
            with store.connection() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM events').fetchone()[0],0)

    def test_coordinator_lock_target_checked_before_open(self):
        from ai_manager.inference import InferenceError
        with synthetic_source(1) as (folder,root):
            store,saved,approval=self.prepared(folder,root)
            batch=store.consume(saved['plan_id'],approval['approval_id'])['batch_id']
            with patch('ai_manager.validation_coordinator.regular',side_effect=InferenceError('unsafe_local_path')):
                with patch('ai_manager.validation_coordinator.FileOwner',side_effect=AssertionError('must_not_open')):
                    with self.assertRaises(InferenceError):Coordinator(store).run(batch)

    def test_metadata_toctou_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'config.json';path.write_bytes(b'{"a":1}')
            original=intake.safe_path;calls=[0]
            def changing(*args,**kwargs):
                calls[0]+=1
                if calls[0]==3:path.write_bytes(b'{"changed":true}')
                return original(*args,**kwargs)
            with patch.object(intake,'safe_path',side_effect=changing):
                with self.assertRaisesRegex(ContractError,'source_changed'):intake.read_small(root,'config.json',100)

    def test_same_physical_root_different_alias_not_config_dedupe(self):
        with synthetic_source(1) as (folder,root):
            a=intake.observe_local(root,alias='alias-a');b=intake.observe_local(root,alias='alias-b')
            self.assertEqual(a['source_identity'],b['source_identity'])
            self.assertEqual(a['candidates'][0]['candidate_id'],b['candidates'][0]['candidate_id'])
            store=ValidationStore(folder/'home',initialize=True)
            store.save_plan(build_plan(a))
            with self.assertRaisesRegex(ContractError,'duplicate_source_active_plan'):store.save_plan(build_plan(b))

    def test_normal_journal_disappearance_is_not_scope_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            store=ValidationStore(Path(directory)/'home',initialize=True)
            original=Path.lstat
            def disappearing(path,*args,**kwargs):
                if str(path).endswith('-journal'):raise FileNotFoundError()
                return original(path,*args,**kwargs)
            with patch.object(Path,'lstat',disappearing):
                with store.connection() as db:self.assertEqual(db.execute('SELECT 1').fetchone()[0],1)

    def test_db_disappearing_before_connect_is_not_recreated(self):
        with tempfile.TemporaryDirectory() as directory:
            store=ValidationStore(Path(directory)/'home',initialize=True)
            original=sqlite3.connect
            def disappeared(*args,**kwargs):
                store.db.unlink()
                return original(*args,**kwargs)
            with patch('ai_manager.validation_store.sqlite3.connect',side_effect=disappeared):
                with self.assertRaisesRegex(ContractError,'no_auto_reset'):
                    with store.connection():self.fail('must_not_yield')
            self.assertFalse(store.db.exists())

    def test_parent_directory_swap_rejected_before_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);root=base/'allowed';outside=base/'outside';root.mkdir();outside.mkdir()
            (root/'config.json').write_bytes(b'{"allowed":true}')
            (outside/'config.json').write_bytes(b'{"outside":true}')
            original=intake.safe_path;fdopen=os.fdopen;swapped=[False]
            def changing(*args,**kwargs):
                result=original(*args,**kwargs)
                if not swapped[0]:
                    swapped[0]=True;root.rename(base/'original');outside.rename(root)
                return result
            class NoRead:
                def __init__(self,stream):self.stream=stream
                def __enter__(self):return self
                def __exit__(self,*args):self.stream.close()
                def fileno(self):return self.stream.fileno()
                def read(self,*args):raise AssertionError('outside_bytes_must_not_be_read')
            with patch.object(intake,'safe_path',side_effect=changing),patch.object(os,'fdopen',side_effect=lambda *a,**k:NoRead(fdopen(*a,**k))):
                with self.assertRaisesRegex(ContractError,'source_parent_changed'):intake.read_small(root,'config.json',100)

    def test_intermediate_directory_swap_rejected_before_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);root=base/'allowed';root.mkdir();nested=root/'nested';nested.mkdir();outside=base/'outside';outside.mkdir()
            (nested/'config.json').write_bytes(b'{"allowed":true}');(outside/'config.json').write_bytes(b'{"outside":true}')
            original=intake.safe_path;swapped=[False]
            def changing(*args,**kwargs):
                result=original(*args,**kwargs)
                if not swapped[0]:swapped[0]=True;nested.rename(base/'original');outside.rename(nested)
                return result
            with patch.object(intake,'safe_path',side_effect=changing):
                with self.assertRaisesRegex(ContractError,'source_parent_changed'):intake.read_small(root,'nested/config.json',100)


if __name__=='__main__':unittest.main()
