import copy
import hashlib
import json
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from ai_manager.drive import FOLDER,DriveError
from ai_manager.validation_contracts import ContractError
from ai_manager.validation_drive import LiveDriveIntake
from ai_manager.validation_profiles import catalog
from ai_manager.validation_intake import observe_drive_inventory


class FakeDrive:
    def __init__(self):
        self.raw=b'{"model_type":"new-synthetic-probe"}'
        self.root=dict(id='root',name='fixture',mimeType=FOLDER,parents=[],trashed=False,version='1')
        self.file=dict(id='config',name='config.json',mimeType='application/json',parents=['root'],size=str(len(self.raw)),trashed=False,version='1')
        self.fail=None;self.change=False;self.partial=False;self.read_ids=[]
    def metadata(self,fid):
        if self.fail:raise DriveError(self.fail)
        result=copy.deepcopy(self.root if fid=='root' else self.file)
        if self.change and fid=='config':result['version']='2'
        return result
    def children(self,parent,token=None):
        return dict(files=[copy.deepcopy(self.file)],incompleteSearch=self.partial)
    def content(self,fid,size=None):
        self.read_ids.append(fid)
        yield self.raw


class DriveIntakeTests(unittest.TestCase):
    def provider(self,drive):
        return LiveDriveIntake(drive,dict(accounts={'A':'synthetic','B':'synthetic'},allowlist=[dict(account='A',id='root')]),'A','root')

    def test_live_metadata_interface_and_stale(self):
        drive=FakeDrive();provider=self.provider(drive)
        first=provider.observe();self.assertTrue(first['complete']);self.assertTrue(first['current_drive_verified'])
        self.assertFalse(first['model_test_performed']);self.assertEqual(drive.read_ids,['config'])
        self.assertEqual(provider.reobserve(first)['fingerprint'],first['fingerprint'])
        drive.file['version']='2'
        with self.assertRaisesRegex(ContractError,'source_stale'):provider.reobserve(first)

    def test_permission_partial_and_source_change_are_not_verified(self):
        for code in ('http_403','http_404','network_retry_exhausted'):
            drive=FakeDrive();drive.fail=code;result=self.provider(drive).observe()
            self.assertFalse(result['current_drive_verified']);self.assertFalse(result['absence_means_deleted'])
        for field in ('partial','change'):
            drive=FakeDrive();setattr(drive,field,True)
            result=self.provider(drive).observe();self.assertFalse(result['complete'])

    def test_scope_shortcut_parent_and_size_budgets(self):
        for change in ('parent','shortcut','size','overflow','unsafe'):
            drive=FakeDrive()
            if change=='parent':drive.file['parents']=['outside']
            if change=='shortcut':drive.file['mimeType']='application/vnd.google-apps.shortcut'
            if change=='size':drive.file['size']='32769'
            if change=='overflow':drive.raw+=b'extra'
            if change=='unsafe':drive.file['name']='../config.json'
            result=self.provider(drive).observe();self.assertFalse(result['complete'],change)
        with self.assertRaisesRegex(ContractError,'not_allowlisted'):
            LiveDriveIntake(FakeDrive(),dict(allowlist=[]),'A','root')

    def test_weight_body_is_never_requested(self):
        drive=FakeDrive();drive.file.update(id='weight',name='bootstapir_checkpoint_v2.pt',mimeType='application/octet-stream',size='218886140')
        result=self.provider(drive).observe()
        self.assertEqual(drive.read_ids,[])
        self.assertEqual(result['candidates'][0]['identity'],'unknown')
        self.assertEqual(result['candidates'][0]['weak_hints'][0]['profile_id'],'tapir')

    def test_cached_export_cannot_be_live_or_dispatchable(self):
        value=dict(schema_version=1,scope_alias='synthetic',scan_id='new_scan',observed_at='2026-10-19',status='partial',files=[])
        result=observe_drive_inventory(value)
        self.assertFalse(result['current_drive_verified']);self.assertFalse(result['dispatchable']);self.assertFalse(result['absence_means_deleted'])

    def test_metadata_network_budget_reserved_before_reobservation(self):
        from ai_manager.validation_store import ValidationStore,build_plan
        drive=FakeDrive();provider=self.provider(drive);observation=provider.observe()
        with tempfile.TemporaryDirectory() as directory:
            store=ValidationStore(Path(directory)/'home',initialize=True,reobserver=provider.reobserve)
            plan=build_plan(observation);plan['limits']['metadata_network_bytes']=2097152
            saved=store.save_plan(plan)
            with patch.object(provider,'reobserve',side_effect=AssertionError('must_not_read')):
                with self.assertRaisesRegex(ContractError,'metadata_network_budget_exceeded'):
                    store.approve(saved['plan_id'],saved['plan_sha256'],confirmed=True)
            self.assertEqual(store.plan(saved['plan_id'])['network_reserved'],2097152)

    def test_same_name_different_ids_both_orders_and_casefold(self):
        for reverse in (False,True):
            for second_name in ('config.json','CONFIG.JSON'):
                drive=FakeDrive();a=copy.deepcopy(drive.file);b=copy.deepcopy(drive.file)
                bad=b'{"model_type":"different_synthetic_content"}'
                b.update(id='other',name=second_name,size=str(len(bad)))
                files=[a,b]
                if reverse:files.reverse()
                original_metadata=drive.metadata
                def metadata(fid):return copy.deepcopy(a if fid=='config' else b) if fid in ('config','other') else original_metadata(fid)
                profiles,cat=catalog();key='qwen3-tts-0.6b-customvoice'
                manifests={key:dict(revision=profiles[key]['revision'],files=[dict(path='config.json',size=len(drive.raw),sha256=hashlib.sha256(drive.raw).hexdigest())])}
                with patch.object(drive,'children',return_value=dict(files=files)),patch.object(drive,'metadata',side_effect=metadata),patch.object(drive,'content',side_effect=lambda fid,size=None:iter([drive.raw if fid=='config' else bad])),patch('ai_manager.validation_drive.manifest_table',return_value=(profiles,cat,manifests)):
                    result=self.provider(drive).observe()
                self.assertFalse(result['complete']);self.assertFalse(result['current_drive_verified'])
                self.assertIn('drive_ambiguous_name',{e['reason'] for e in result['errors']})
                self.assertTrue(all(c['identity']!='supported_metadata' for c in result['candidates']))
                from ai_manager.validation_store import build_plan
                with self.assertRaisesRegex(ContractError,'not_dispatchable'):build_plan(result)

    def test_same_id_duplicate_is_not_different_source(self):
        drive=FakeDrive()
        with patch.object(drive,'children',return_value=dict(files=[drive.file,copy.deepcopy(drive.file)])):
            result=self.provider(drive).observe()
        self.assertFalse(result['complete'])
        self.assertEqual(result['errors'][0]['reason'],'drive_duplicate_observation')


if __name__=='__main__':unittest.main()
