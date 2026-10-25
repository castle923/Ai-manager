import contextlib,importlib.util,io,json,os,pathlib,tempfile,unittest
from unittest.mock import patch
BASE=pathlib.Path(__file__).parent.parent/'scripts/colab'
spec=importlib.util.spec_from_file_location('file_result_check',BASE/'file_result_check.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
CANARY='PRIVATE_CANARY_NEVER_EXPORTED_123456789'
class FileResultTests(unittest.TestCase):
 def setUp(self):
  tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=pathlib.Path(tmp.name)
  self.work=self.root/'inference-watchdog-fixed';self.work.mkdir()
  self.ns=dict(ROOT=self.root,PY=self.root/'venv/bin/python',META=self.root/'metadata-proof.json',FRESH_META_TIME=12,
   FRESH_META={'status':'INT8_preflight_candidate'},PAYLOADS={'test':{'sha256':'synthetic'}},env=lambda offline:{},
   load_reviewed=lambda *args:None,WORK=self.work,TOKEN=CANARY,
   DOWNLOAD={'status':'completed','file_count':10,'total_bytes':16069722669,'full_weight_SHA_verified':True,'token_saved':False,'model_path':str(self.root/'model')})
  self.ns['RUNTIME_CONTEXT']=eval(m.CONTEXT_VALUE,{'globals':lambda:self.ns,'json':json})
  self.ns['DOWNLOAD_CONTEXT']=(self.ns['RUNTIME_CONTEXT'],self.ns['load_reviewed'])
 def inspect(self):
  with patch.object(m,'_root_valid',return_value=True):return m.inspect_file_results(self.ns)
 def write(self,name,value):
  (self.work/name).write_text(json.dumps(value),encoding='utf-8')
 def test_finished_result_and_guard_recovered_without_secret_pid_or_text(self):
  self.write('watchdog-summary.json',{'status':'completed','reason':'worker_exited','gate_opened':True,'worker_returncode':0,'final_worker_returncode':0,'remaining_owned_count':0,'elapsed_seconds':25.5,'pid':88888888,'secret':CANARY})
  self.write('phase.json',{'stage':'done','history':[{'stage':'load_begin','monotonic_seconds':3,'secret':CANARY},{'stage':'done','monotonic_seconds':25}]})
  self.write('result.json',{'status':'single_Llama_LLM_INT8_GPU_smoke_pass','generation_calls':1,'new_tokens':3,'eos_reached':True,'loading_seconds':20,'inference_seconds':1,'output_text':CANARY,'input_text':CANARY,'pid':88888888,'parameter_residency':{'quantized_linear_count':224,'cpu_parameter_bytes':0,'secret':CANARY},'device_map':{'private-module-name':0,'other':'cpu'}})
  (self.work/'worker.stderr.log').write_text('Warning '+CANARY+' Loading checkpoint shards: 100%',encoding='utf-8')
  before=dict(self.ns);r=self.inspect();self.assertEqual(before,self.ns)
  self.assertTrue(r['finished_result_evidence']);self.assertTrue(r['guard_clean_completion_evidence'])
  text=json.dumps(r,allow_nan=False)
  for secret in (CANARY,'88888888',str(self.root),'private-module-name','output_text','input_text'):self.assertNotIn(secret,text)
  self.assertTrue(r['files']['worker.stderr.log']['markers']['loading_shards'])
 def test_partial_phase_and_stderr_markers_do_not_claim_completion(self):
  self.write('phase.json',{'stage':'load_begin','history':[{'stage':'load_begin','monotonic_seconds':3}]})
  (self.work/'worker.stderr.log').write_bytes(b'Traceback (most recent call last)\nOutOfMemoryError\n')
  r=self.inspect();self.assertFalse(r['finished_result_evidence']);self.assertFalse(r['guard_clean_completion_evidence'])
  self.assertTrue(r['files']['worker.stderr.log']['markers']['traceback']);self.assertTrue(r['files']['worker.stderr.log']['markers']['oom'])
 def test_oversize_files_are_not_read(self):
  (self.work/'result.json').write_bytes(b'x'*65537);(self.work/'worker.stderr.log').write_bytes(b'x'*16385)
  original=m._bounded_read
  def checked(path,limit):
   self.assertNotIn(path.name,('result.json','worker.stderr.log'));return original(path,limit)
  with patch.object(m,'_bounded_read',side_effect=checked):r=self.inspect()
  self.assertTrue(r['files']['result.json']['oversize']);self.assertFalse(r['files']['result.json']['readable'])
 def test_context_root_and_work_mismatch_never_read_files(self):
  for key,value in {'ROOT':pathlib.Path('/content/llama-t4-int8-other'),'FRESH_META_TIME':13,'load_reviewed':lambda *args:None,'WORK':self.root/'other'}.items():
   with self.subTest(key=key):
    old=self.ns[key];self.ns[key]=value
    with patch.object(m,'_bounded_read',side_effect=AssertionError('must_not_read')):r=self.inspect()
    self.assertEqual(r['files'],{});self.ns[key]=old
  with patch.object(m,'_root_valid',return_value=False),patch.object(m,'_bounded_read',side_effect=AssertionError('must_not_read')):r=m.inspect_file_results(self.ns)
  self.assertEqual(r['files'],{})
 def test_bounded_reader_regular_read_limit_and_symlink_rejection(self):
  p=self.work/'result.json';p.write_bytes(b'{}');self.assertEqual(m._bounded_read(p,2),b'{}')
  with self.assertRaises(ValueError):m._bounded_read(p,1)
  with patch.object(pathlib.Path,'is_symlink',return_value=True),patch.object(os,'open',side_effect=AssertionError('must_not_open')):
   with self.assertRaises(ValueError):m._bounded_read(p,2)
 def test_unknown_strings_nonfinite_numbers_and_invalid_json_are_not_exported(self):
  self.write('result.json',{'status':CANARY,'reason':CANARY,'new_tokens':float('nan'),'parameter_residency':{'pid':88888888,'secret':CANARY}})
  (self.work/'phase.json').write_bytes(b'invalid json '+CANARY.encode())
  r=self.inspect();self.assertFalse(r['finished_result_evidence']);self.assertFalse(r['files']['phase.json']['readable'])
  text=json.dumps(r,allow_nan=False);self.assertNotIn(CANARY,text);self.assertNotIn('NaN',text)
 def test_missing_context_prints_fixed_not_ready_without_filesystem_calls(self):
  output=io.StringIO()
  with patch.object(os,'open',side_effect=AssertionError('no_file_read')),patch.object(pathlib.Path,'stat',side_effect=AssertionError('no_file_metadata')),contextlib.redirect_stdout(output):
   m.print_file_result_check({})
  self.assertEqual(output.getvalue(),'__RESULT_CHECK_SKIPPED__'+json.dumps({'status':'not_ready','reason':'live_context_absent'},sort_keys=True)+'\n')
 def test_new_guard_telemetry_enums_and_numbers_are_whitelisted(self):
  data={'status':'stopped','reason':'worker_exit_confirmation_timeout','primary_reason':'worker_exit_confirmation_timeout','identity_observation':'owned_zombie','exit_poll_path':'main_poll','exit_confirmation_samples':4,'exit_confirmation_seconds':1.0,'secret':CANARY}
  self.assertEqual(m._whitelist(data),{k:v for k,v in data.items() if k!='secret'})
  self.assertNotIn('identity_observation',m._whitelist({'identity_observation':CANARY}))
  self.assertNotIn('exit_poll_path',m._whitelist({'exit_poll_path':CANARY}))
if __name__=='__main__':unittest.main(verbosity=2)
