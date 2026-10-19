"""M14 fresh-store API/lifecycle negatives; synthetic data is never model proof."""
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import requests
from ai_manager.server import create_application
from ai_manager.validation_ui import ValidationUI
from ai_manager.validation_contracts import ContractError
from test_validation_control import synthetic_source


class Auth:
    class Store:
        def get(self, account): return None
    store = Store()


def body(root, action='run_cpu_probe'):
    return dict(roots=[str(root)],action=action,runtimes={},wall_seconds=120,source='local',drive_scope=0)


class UIContracts(unittest.TestCase):
    def test_explicit_action_sha_approval_one_consumption_history_new_plan(self):
        with synthetic_source(1) as (folder,root):
            service=ValidationUI(folder/'app')
            plan=service.create_plan(body(root))
            self.assertFalse(plan['model_test_performed'])
            with self.assertRaisesRegex(ContractError,'approval_action_mismatch'):
                service.approve(dict(plan_id=plan['plan_id'],plan_sha256=plan['plan_sha256'],confirmed=True,action='run_models'))
            with self.assertRaisesRegex(ContractError,'approval_plan_mismatch'):
                service.approve(dict(plan_id=plan['plan_id'],plan_sha256='0'*64,confirmed=True,action=plan['action']))
            grant=service.approve(dict(plan_id=plan['plan_id'],plan_sha256=plan['plan_sha256'],confirmed=True,action=plan['action']))
            dispatch=dict(plan_id=plan['plan_id'],approval_id=grant['approval']['id'])
            first=service.start(dispatch)
            service.worker.join(20)
            self.assertFalse(service.worker.is_alive())
            again=service.start(dispatch)
            self.assertEqual(first['batch_id'],again['batch_id'])
            self.assertEqual(again['status'],'control_validated')
            self.assertFalse(again['model_test_performed'])
            self.assertEqual(again['cases'][0]['status'],'probe_succeeded')
            self.assertEqual(again['cases'][0]['output'],'not_verified')
            nextplan=service.create_plan(body(root))
            self.assertNotEqual(plan['plan_id'],nextplan['plan_id'])
            self.assertNotEqual(plan['cases'][0]['case_id'],nextplan['cases'][0]['case_id'])
            self.assertEqual(len(service.history()['plans']),2)
            self.assertIsNone(nextplan['approval'])
            service.close()

    def test_source_changed_never_approved_and_store_corruption_preserved(self):
        with synthetic_source(1) as (folder,root):
            service=ValidationUI(folder/'app');plan=service.create_plan(body(root))
            (root/'model0/weight.bin').write_bytes(b'changed')
            with self.assertRaisesRegex(ContractError,'source_stale'):
                service.approve(dict(plan_id=plan['plan_id'],plan_sha256=plan['plan_sha256'],confirmed=True,action=plan['action']))
            self.assertTrue(service.detail(plan['plan_id'])['stale'])
            self.assertIsNone(service.detail(plan['plan_id'])['approval'])
            service.close()
        with tempfile.TemporaryDirectory() as directory:
            service=ValidationUI(Path(directory)/'app');service.home.mkdir(parents=True)
            corrupt=service.home/'validation-control.sqlite3';corrupt.write_bytes(b'keep-corrupt')
            with self.assertRaises(ContractError):service.initialize()
            self.assertEqual(corrupt.read_bytes(),b'keep-corrupt')

    def test_native_app_close_cancels_owned_cpu_probe(self):
        with synthetic_source(1) as (folder,root):
            app=create_application(folder/'app',{'allowlist':[]},Auth())
            service=app.validation
            plan=service.create_plan(body(root));store=service.store()
            # A separate long CPU plan is generated before approval, never mutate a saved plan.
            with store.transaction() as db:db.execute('UPDATE plans SET invalid=1 WHERE id=?',(plan['plan_id'],))
            from ai_manager.validation_store import build_plan
            from ai_manager.validation_intake import observe_local
            saved=store.save_plan(build_plan(observe_local(root),action='run_cpu_probe',wall_seconds=120,probe_seconds=20,timeout_seconds=30))
            grant=store.approve(saved['plan_id'],saved['plan_sha256'],confirmed=True)
            service.start(dict(plan_id=saved['plan_id'],approval_id=grant['approval_id']))
            deadline=time.monotonic()+10
            while time.monotonic()<deadline and not any(c['status']=='running' for c in store.status(service.detail(saved['plan_id'])['batch_id'])['cases']):time.sleep(.02)
            app.close()
            self.assertFalse(service.worker.is_alive())
            self.assertEqual(service.detail(saved['plan_id'])['status'],'cancelled')

    def test_http_guard_client_plan_rejected_drive_no_auth_dispatch_zero(self):
        with synthetic_source(1) as (folder,root):
            app=create_application(folder/'app',{'allowlist':[dict(account='A',id='test-root')]},Auth())
            url=app.start().rstrip('/')
            try:
                token=requests.get(url+'/api/session',timeout=5).json()['csrf']
                headers={'Content-Type':'application/json','X-AiManager-CSRF':token}
                endpoint=url+'/api/validation/plan'
                self.assertEqual(requests.post(endpoint,json=body(root),timeout=5).status_code,403)
                self.assertEqual(requests.post(endpoint,json=body(root),headers=dict(headers,Origin='https://foreign.invalid'),timeout=5).status_code,403)
                result=requests.get(url+'/api/validation/scopes',timeout=5).json()
                self.assertFalse(result['drive_scopes'][0]['connected'])
                data=body(root);data.update(source='drive',roots=[],action='validate_control_plan')
                result=requests.post(endpoint,json=data,headers=headers,timeout=5)
                self.assertEqual(result.json()['error'],'drive_not_connected_user_login_required')
                data=body(root);data['plan']={}
                self.assertEqual(requests.post(endpoint,json=data,headers=headers,timeout=5).status_code,409)
                result=requests.post(endpoint,json=body(root),headers=headers,timeout=5)
                self.assertEqual(result.status_code,200,result.text)
                self.assertEqual(result.json()['action'],'run_cpu_probe')
                self.assertEqual(requests.get(url+'/api/validation',timeout=5).json()['plans'][0]['status'],None)
            finally:app.close()


if __name__=='__main__':unittest.main()
