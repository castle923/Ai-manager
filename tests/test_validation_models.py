"""Fresh synthetic M13 negatives; no model/credential/network dependencies."""
import hashlib
import json
import math
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import wave
from ai_manager import validation_models as m
from ai_manager.validation_contracts import ContractError
from ai_manager.validation_store import build_plan,ValidationStore,control_code_sha


class ModelContracts(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)

    def test_full_hash_all_bytes_not_size_metadata(self):
        path=self.root/'weights.bin';path.write_bytes(b'fresh-weight')
        manifest=dict(files=[dict(path=path.name,size=12,sha256=hashlib.sha256(path.read_bytes()).hexdigest())])
        proof=m.full_hash(self.root,manifest)
        self.assertEqual(proof[0]['bytes'],12)
        path.write_bytes(b'other-weight')
        with self.assertRaisesRegex(ContractError,'model_integrity_failed'):m.full_hash(self.root,manifest)

    def test_hash_cancel_before_io(self):
        def cancel():raise ContractError('cancelled')
        with self.assertRaisesRegex(ContractError,'cancelled'):m.full_hash(self.root,dict(files=[dict(path='missing',size=1,sha256='0'*64)]),cancel)

    def test_hash_escape_rejected(self):
        with self.assertRaises(ContractError):m.full_hash(self.root,dict(files=[dict(path='../escape',size=1,sha256='0'*64)]))

    def test_anchor_policy_leaves_large_tokenizer_for_full_hash(self):
        from ai_manager.validation_intake import observe_local
        (self.root/'config.json').write_text('{}');(self.root/'tokenizer_config.json').write_bytes(b'x'*300000)
        regular=observe_local(self.root)
        anchors=observe_local(self.root,metadata_anchors_only=True)
        self.assertFalse(regular['complete']);self.assertTrue(anchors['complete'])
        self.assertEqual(next(f for f in anchors['files'] if f['path']=='tokenizer_config.json')['bytes'],300000)
        self.assertNotIn('sha256',next(f for f in anchors['files'] if f['path']=='tokenizer_config.json'))

    def test_runtime_lock_only_eol_equivalence(self):
        python=self.root/'python.exe';python.write_bytes(b'fake executable')
        lock=self.root/'requirements.lock';lock.write_bytes(m.task_runtime.requirements('tapir').read_bytes().replace(b'\r\n',b'\n').replace(b'\n',b'\r\n'))
        binding=m.runtime_binding(str(python),str(lock),'tapir')
        self.assertEqual(binding['lock_sha256'],m.digest(lock))
        lock.write_bytes(lock.read_bytes()+b'newpackage==9\r\n')
        with self.assertRaisesRegex(ContractError,'runtime_lock_mismatch'):m.runtime_binding(str(python),str(lock),'tapir')

    def test_fresh_common_tts_bytes_independent_files(self):
        first=self.root/'one';second=self.root/'two';first.mkdir();second.mkdir()
        a=m.fresh_input('qwen3-tts-0.6b-customvoice','a','c',first)
        b=m.fresh_input('qwen3-tts-1.7b-customvoice','a','d',second)
        self.assertEqual(a[0],b[0]);self.assertNotEqual(a[2]['case_id'],b[2]['case_id'])
        with self.assertRaises(FileExistsError):m.fresh_input('qwen3-tts-0.6b-customvoice','a','c',first)

    def test_stt_never_falls_back_to_past_audio(self):
        with self.assertRaisesRegex(ContractError,'deferred_dependency'):m.fresh_input('whisper-large-v3-turbo','a','b',self.root)

    def test_same_batch_audio_transform_lineage(self):
        source=self.root/'source';target=self.root/'target';source.mkdir();target.mkdir()
        values=[int(1200*math.sin(i/13)) for i in range(24000)]
        import struct
        with wave.open(str(source/'output.wav'),'wb') as w:
            w.setparams((1,2,24000,0,'NONE','not compressed'));w.writeframes(struct.pack('<'+'h'*len(values),*values))
        dependency=dict(batch_id='batch',directory=str(source),run_id='run',case_id='case',outputs=[dict(sha256=m.digest(source/'output.wav'))])
        data,info,lineage=m.fresh_input('whisper-large-v3-turbo','batch','stt',target,dependency)
        self.assertEqual(info['sample_rate'],16000);self.assertEqual(info['frames'],16000)
        self.assertEqual(lineage['source_sha256'],dependency['outputs'][0]['sha256']);self.assertEqual(lineage['source_run'],'run')
        dependency['outputs'][0]['sha256']='0'*64
        with self.assertRaisesRegex(ContractError,'dependency_changed'):m.fresh_input('whisper-large-v3-turbo','batch','stt',target,dependency)

    def test_all_six_reject_process_exit_only(self):
        for profile in m.manifest_table()[2]:
            with self.subTest(profile=profile),self.assertRaises(ContractError):
                m.validate_outputs(profile,self.root,dict(run_id='r',input_sha256='0'*64),dict(status='generated',run_id='r',input_sha256='0'*64),0)

    def test_all_six_reject_foreign_run(self):
        for profile in m.manifest_table()[2]:
            with self.subTest(profile=profile),self.assertRaises(ContractError):
                m.validate_outputs(profile,self.root,dict(run_id='r',input_sha256='0'*64),dict(status='generated',run_id='foreign',input_sha256='0'*64),0)

    def test_all_six_reject_nan_metrics(self):
        for profile in m.manifest_table()[2]:
            with self.subTest(profile=profile),self.assertRaisesRegex(ContractError,'output_invalid'):
                m.validate_outputs(profile,self.root,dict(run_id='r',input_sha256='0'*64),dict(status='generated',run_id='r',input_sha256='0'*64,metrics=dict(loading_seconds=float('nan'))),0)

    def test_tts_silence_output_rejected(self):
        with wave.open(str(self.root/'output.wav'),'wb') as w:w.setparams((1,2,24000,0,'NONE',''));w.writeframes(b'\0'*48000)
        with self.assertRaises(ValueError):m.validate_wav(self.root/'output.wav')

    def test_control_approval_cannot_supply_model_spec(self):
        with self.assertRaisesRegex(ContractError,'model_authority_forbidden'):build_plan({},model_spec={})

    def test_no_model_action_without_spec(self):
        with self.assertRaisesRegex(ContractError,'model_spec_required'):build_plan({},action='run_models')

    def test_codegen_hash_covers_new_worker(self):
        original=control_code_sha();source=Path(m.__file__).parent/'validation_env_probe.py'
        old=Path.read_bytes
        def changed(path):return old(path)+(b'\n# changed' if path==source else b'')
        with patch.object(Path,'read_bytes',changed):self.assertNotEqual(control_code_sha(),original)

    def test_runtime_change_is_rejected(self):
        with patch.object(m,'runtime_binding',return_value=dict(changed=True)):
            with self.assertRaisesRegex(ContractError,'runtime_changed'):m.check_binding(dict(python='p',lock='l'),'tapir')

    def test_resource_gate_blocks_before_model(self):
        (self.root/'environment.log').write_text(json.dumps(dict(packages={},cuda_available=True,ram_available_bytes=2**40,gpu_free_bytes=1,disk_free_bytes=2**40)))
        with patch.object(m,'check_binding'),patch.object(m,'_owned',return_value=0):
            with self.assertRaisesRegex(ContractError,'resource_blocked'):m.preflight(dict(python='p',packages={}),'llama-3.1-8b-instruct',self.root,lambda:None,threading.Event())

    def test_missing_runtime_dispatch_zero(self):
        plan=dict(model_spec=dict(runtimes={}))
        with patch.object(m,'_owned') as spawn:
            with self.assertRaisesRegex(ContractError,'runtime_not_designated'):m.execute(None,'batch',dict(profile_id='qwen-image-2.1'),plan,self.root,lambda:None,threading.Event())
            spawn.assert_not_called()

    def test_duplicate_root_rejected(self):
        with self.assertRaisesRegex(ContractError,'model_scope_duplicate'):m.observe_scopes([str(self.root),str(self.root)])


if __name__=='__main__':unittest.main()
