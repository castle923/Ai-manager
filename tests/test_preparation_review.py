"""Fresh independent M3 adversarial tests; synthetic assets only."""
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from ai_manager.drive import DriveError, FOLDER
from ai_manager.preparation import Preparation, PreparationError, safe_relative, ACTIVE, MODEL_SEGMENT

PAYLOAD = b'new independent review input'
DIGEST = hashlib.sha256(PAYLOAD).hexdigest()
MANIFEST = dict(name='synthetic model', model_id='review', revision='review-revision', source='https://example.invalid/review', files=[dict(path='config.json',size=len(PAYLOAD),sha256=DIGEST),dict(path='speech_tokenizer/model.safetensors',size=len(PAYLOAD),sha256=DIGEST)])

def metadata(fid, name, parent, mime='application/octet-stream'):
    return dict(id=fid,name=name,parents=[parent],mimeType=mime,size=str(len(PAYLOAD)),version='1',modifiedTime='2026-10-16T00:00:00Z',sha256Checksum=DIGEST)

class FakeDrive:
    def __init__(self, access=None, cancel=None):
        self.cancel=cancel
        self.items={'root':dict(id='root',name='approved',mimeType=FOLDER), 'model':dict(id='model',name=MODEL_SEGMENT,parents=['root'],mimeType=FOLDER), 'speech':dict(id='speech',name='speech_tokenizer',parents=['model'],mimeType=FOLDER), 'config':metadata('config','config.json','model'), 'weight':metadata('weight','model.safetensors','speech')}
        self.calls=[]; self.contents=0; self.fail=None; self.after_change=None
    def metadata(self,fid):
        self.calls.append(fid)
        result=dict(self.items[fid])
        if self.after_change and self.contents and fid=='config':result.update(self.after_change)
        return result
    def children(self,fid,token=None):
        return {'files':[dict(v) for v in self.items.values() if fid in v.get('parents',[])]}
    def content(self,fid,size=None):
        self.contents+=1
        if self.fail=='network':
            yield PAYLOAD[:4]
            raise DriveError('download_network_interrupted')
        if self.fail=='cancel':self.cancel.set()
        yield b'x'*len(PAYLOAD) if self.fail=='hash' else PAYLOAD

class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.home=Path(self.temp.name);self.drive=FakeDrive()
        self.prep=Preparation(self.home,{'allowlist':[{'account':'B','id':'root'}]},object(),lambda *a,**kw:self.drive)
        self.drive.cancel=threading.Event()
        self.observed=[{'path':'B_ROOT/'+MODEL_SEGMENT+'/config.json','metadata':self.drive.items['config']}]
        self.addCleanup(patch.stopall)
        patch('ai_manager.preparation.manifest',return_value=MANIFEST).start()
        patch.object(self.prep,'_observed',side_effect=lambda:self.observed).start()
    def run_prepare(self):return self.prep.prepare(self.drive.cancel)
    def assets(self):return list(self.prep.base.glob('*/assets/**/model.safetensors'))+list(self.prep.base.glob('*/assets/config.json'))
    def test_new_bytes_and_manifest_hashes_publish(self):
        state=self.run_prepare();self.assertEqual(state['status'],'ready');self.assertEqual(state['files_verified'],2)
        for file in self.assets():self.assertEqual(hashlib.sha256(file.read_bytes()).hexdigest(),DIGEST)
        self.assertFalse(list(self.prep.base.rglob('*.part')))
    def test_unsafe_windows_paths(self):
        for name in ('../x','a/../x','/x','C:/x','a\\x','a//x','a/./x','CON','NUL.txt','com1.json','x.','x ','a:b','x\x00y','x?y'):
            with self.subTest(name=name),self.assertRaises(ValueError):safe_relative(name)
    def test_drive_name_cannot_impersonate_nested_path(self):
        del self.drive.items['weight']
        self.drive.items['injected']=metadata('injected','speech_tokenizer/model.safetensors','model')
        state=self.run_prepare()
        self.assertEqual(state['status'],'failed');self.assertEqual(self.drive.contents,0)
    def test_case_collision_blocks(self):
        altered=dict(MANIFEST,files=MANIFEST['files']+[dict(path='CONFIG.JSON',size=len(PAYLOAD),sha256=DIGEST)])
        self.drive.items['case']=metadata('case','CONFIG.JSON','model')
        with patch('ai_manager.preparation.manifest',return_value=altered):state=self.run_prepare()
        self.assertEqual(state['status'],'failed');self.assertEqual(state['error'],'unsafe_path')
    def test_missing_component_blocks_without_media(self):
        del self.drive.items['weight'];state=self.run_prepare()
        self.assertEqual(state['configuration'],'missing');self.assertEqual(self.drive.contents,0)
    def test_duplicate_source_blocks_without_media(self):
        self.drive.items['duplicate']=metadata('duplicate','config.json','model');state=self.run_prepare()
        self.assertEqual(state['error'],'ambiguous_component');self.assertEqual(self.drive.contents,0)
    def test_outside_ancestry_blocks_without_media(self):
        self.drive.items['model']['parents']=['other'];self.drive.items['other']=dict(id='other',mimeType=FOLDER)
        state=self.run_prepare();self.assertEqual(state['error'],'outside_allowlist');self.assertEqual(self.drive.contents,0)
    def test_disk_full_before_media(self):
        with patch('ai_manager.preparation.shutil.disk_usage',return_value=type('Usage',(),{'free':0})()):state=self.run_prepare()
        self.assertEqual(state['error'],'insufficient_disk');self.assertEqual(self.drive.contents,0);self.assertFalse(self.assets())
    def test_interrupted_network_does_not_publish_partial(self):
        self.drive.fail='network';state=self.run_prepare()
        self.assertEqual(state['error'],'download_network_interrupted');self.assertFalse(self.assets());self.assertTrue(list(self.prep.base.rglob('*.part')))
    def test_cancel_does_not_publish(self):
        self.drive.fail='cancel';state=self.run_prepare()
        self.assertEqual(state['status'],'cancelled');self.assertFalse(self.assets())
    def test_retry_uses_new_run_and_preserves_failed_evidence(self):
        self.drive.fail='network';first=self.run_prepare();first_id=first['id']
        first_evidence=(self.prep.base/first_id/'state.json').read_bytes()
        self.drive.fail=None;second=self.run_prepare()
        self.assertEqual(second['status'],'ready');self.assertNotEqual(first_id,second['id'])
        self.assertEqual((self.prep.base/first_id/'state.json').read_bytes(),first_evidence)
        self.assertTrue(list((self.prep.base/first_id).rglob('*.part')))
    def test_dead_process_nonterminal_is_interrupted(self):
        self.prep.base.mkdir()
        state=dict(id='synthetic-run',pid=99999999,status='downloading',integrity='unverified')
        self.prep.current.write_text(json.dumps(state))
        self.assertEqual(self.prep.snapshot()['preparation']['status'],'interrupted')
    def test_hash_mismatch_does_not_publish(self):
        self.drive.fail='hash';state=self.run_prepare()
        self.assertEqual(state['integrity'],'mismatched');self.assertEqual(state['error'],'hash_mismatch');self.assertFalse(self.assets())
    def test_remote_version_change_after_download_blocks(self):
        self.drive.after_change={'version':'2'};state=self.run_prepare()
        self.assertEqual(state['error'],'source_changed');self.assertFalse(self.assets())
    def test_remote_hash_change_after_download_blocks(self):
        self.drive.after_change={'sha256Checksum':'0'*64};state=self.run_prepare()
        self.assertEqual(state['error'],'source_changed');self.assertFalse(self.assets())
    def test_no_overwrite_existing_target(self):
        original=self.drive.content
        def content(fid,size=None):
            state=json.loads(self.prep.current.read_text());target=self.prep.base/state['id']/'assets'/'config.json'
            target.write_bytes(b'preserved existing bytes')
            yield from original(fid)
        self.drive.content=content;state=self.run_prepare()
        self.assertEqual(state['status'],'failed');self.assertEqual(self.assets()[0].read_bytes(),b'preserved existing bytes')
    def test_concurrent_guard_rejects(self):
        self.assertTrue(ACTIVE.acquire(False))
        try:
            with self.assertRaises(PreparationError):self.run_prepare()
        finally:ACTIVE.release()
    def test_disk_full_during_stream_does_not_publish(self):
        usage=type('Usage',(),{'free':0})()
        real_plan=self.prep.plan
        calls=[0]
        def disk(path):
            calls[0]+=1
            return type('Usage',(),{'free':(10**12 if calls[0]==1 else 0)})()
        with patch('ai_manager.preparation.shutil.disk_usage',side_effect=disk):state=self.run_prepare()
        self.assertEqual(state['error'],'insufficient_disk');self.assertFalse(self.assets())
    def test_lock_open_failure_releases_global_guard(self):
        self.prep.base.mkdir()
        with patch('ai_manager.preparation.Path.open',side_effect=PermissionError('synthetic refusal')):
            try:self.run_prepare()
            except (PermissionError,PreparationError):pass
        held=ACTIVE.locked()
        if held:ACTIVE.release()
        self.assertFalse(held,'local I/O failure leaked global preparation guard')
    def test_runtime_process_timeout_blocks(self):
        import subprocess
        fake=self.home/'runtime'/'venv'/'Scripts'/'python.exe';fake.parent.mkdir(parents=True);fake.write_bytes(b'synthetic executable placeholder')
        with patch('ai_manager.external_process.run_external',side_effect=subprocess.TimeoutExpired('synthetic',120)) as run:
            result=self.prep.probe_runtime()
        run.assert_called_once()
        self.assertEqual(run.call_args.kwargs['timeout'],120)
        self.assertEqual(run.call_args.args[0][0],str(fake))
        self.assertEqual(result['status'],'blocked');self.assertEqual(result['blockers'],['runtime_probe_failed'])
    def test_crossprocess_lock_rejects_before_media(self):
        import msvcrt
        import os
        import subprocess
        import sys
        self.prep.base.mkdir()
        lock=(self.prep.base/'preparation.lock').open('w+b')
        lock.write(b'0');lock.flush();lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        script="from ai_manager.preparation import Preparation,PreparationError; import sys\ntry: Preparation(sys.argv[1]).prepare()\nexcept PreparationError as e: print(str(e))"
        try:
            result=subprocess.run([sys.executable,'-c',script,str(self.home)],capture_output=True,text=True,timeout=15)
        finally:lock.close()
        self.assertEqual(result.returncode,0);self.assertEqual(result.stdout.strip(),'operation_running');self.assertFalse(self.assets())
    def test_removed_asset_cannot_remain_ready(self):
        self.run_prepare();self.assets()[0].unlink()
        state=self.prep.snapshot()['preparation']
        self.assertNotEqual(state['status'],'ready')
        self.assertNotEqual(state['integrity'],'matched')
    def test_public_snapshot_excludes_private_sources(self):
        self.run_prepare();public=json.dumps(self.prep.snapshot())
        self.assertNotIn(str(self.home),public)
        self.assertNotIn('sha256Checksum',public)
        self.assertNotIn('parents',public)
        self.assertNotIn('inputs.json',public)
    def test_missing_runtime_recheck_invalidates_old_ready_record(self):
        record=self.home/'runtime'/'environment.json';record.parent.mkdir();record.write_text(json.dumps({'status':'ready','cuda_available':True,'blockers':[]}))
        result=self.prep.probe_runtime()
        self.assertEqual(result['status'],'blocked')
        self.assertEqual(self.prep.environment()['status'],'blocked')
    def test_missing_runtime_is_blocked(self):
        result=self.prep.probe_runtime();self.assertEqual(result['status'],'blocked');self.assertIn('runtime_dependency_missing',result['blockers'])

if __name__=='__main__':unittest.main()
