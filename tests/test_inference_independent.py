"""Fresh synthetic M4 counterexamples, independent of model/GPU output."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import subprocess
import tempfile
import threading
import time
import unittest
import wave
from types import SimpleNamespace
from unittest.mock import patch
from http.server import ThreadingHTTPServer
import requests

from ai_manager.inference import Inference, InferenceError, validate_wav


FAKE_WORKER = r'''
import hashlib,json,pathlib,struct,sys,time,wave,subprocess
p=pathlib.Path(sys.argv[1]); d=p.parent; r=json.loads(p.read_text(encoding='utf8')); mode=r['text']
if mode in ('sleep','late'): time.sleep(30)
if mode=='crash': sys.exit(9)
if mode=='tree':
 child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'])
 (d/'descendant.pid').write_text(str(child.pid))
result={'run_id':r['id'],'input_sha256':r['input_sha256'],'status':'generated','metrics':{}}
if mode=='oom':
 result.update(status='failed',error='inference_out_of_memory')
elif mode=='badbind': result['input_sha256']='0'*64
else:
 with wave.open(str(d/'output.wav'),'wb') as w:
  w.setparams((1,2,24000,0,'NONE','not compressed')); w.writeframes(struct.pack('<2400h', *([1000,-1000]*1200)))
 if mode=='corrupt': (d/'output.wav').write_bytes(b'corrupt')
(d/'result.json').write_text(json.dumps(result))
'''


class IndependentInferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        self.worker = self.home/'synthetic_worker.py'
        self.worker.write_text(FAKE_WORKER)
        self.processes=[]
        def spawn(*args,**kwargs):
            process=subprocess.Popen(*args,**kwargs);self.processes.append(process);return process
        self.manager = Inference(self.home, timeout=2,popen=spawn)
        def prepare(run):
            (self.manager._path(run['id'])/'request.json').write_text(json.dumps(run))
            return Path(getattr(sys, '_base_executable', sys.executable)), self.worker
        self.manager._prepare = prepare

    def tearDown(self):
        self.manager.close()
        self.temp.cleanup()

    def terminal(self, run, timeout=5):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            value=self.manager.get(run['id'])
            if value['status'] in {'succeeded','failed','cancelled','interrupted'}:
                return value
            time.sleep(.02)
        self.fail('run did not reach terminal state')

    def test_blank_nonstring_controls_and_length_rejected(self):
        for text in ('', '  ', None, [], 'x\x00', '가'*301, '\ud800'):
            with self.subTest(text=repr(text)):
                with self.assertRaises(InferenceError): self.manager.create(text)
        self.assertEqual(self.manager.snapshot()['runs'], [])

    def test_run_id_path_url_code_injection_rejected(self):
        for value in ('../x', 'https://x.invalid', 'x;whoami', 'A'*32, '0'*31, None):
            with self.subTest(value=value):
                with self.assertRaises(InferenceError): self.manager.get(value)

    def test_text_is_data_and_input_hash_is_fresh(self):
        text="'; __import__('os').system('echo unsafe'); #"
        run=self.terminal(self.manager.create(text))
        self.assertEqual(run['input_sha256'], hashlib.sha256(text.encode()).hexdigest())
        self.assertEqual(run['text'],text)
        self.assertEqual(run['status'],'succeeded')

    def test_completed_audio_revalidated_after_corruption(self):
        run=self.terminal(self.manager.create('valid'))
        self.assertEqual(run['status'],'succeeded')
        self.assertGreater(len(self.manager.audio(run['id'])),44)
        (self.manager._path(run['id'])/'output.wav').write_bytes(b'corrupt')
        with self.assertRaisesRegex(InferenceError,'output_invalid'): self.manager.audio(run['id'])

    def test_timeout_not_success_and_owned_child_gone(self):
        run=self.terminal(self.manager.create('sleep'))
        self.assertEqual((run['status'],run['error']),('failed','inference_timeout'))
        self.assertIsNone(run['audio_url'])
        self.assertIsNone(self.manager.child)
        self.assertTrue(all(process.poll() is not None for process in self.processes))

    def test_crash_oom_corrupt_binding_never_complete(self):
        for text,error in [('crash','worker_crashed'),('oom','inference_out_of_memory'),('corrupt','output_invalid'),('badbind','worker_crashed')]:
            with self.subTest(text=text):
                run=self.terminal(self.manager.create(text))
                self.assertEqual((run['status'],run['error']),('failed',error))
                self.assertIsNone(run['audio_url'])

    def test_cancel_active_and_queued_no_audio(self):
        first=self.manager.create('sleep')
        end=time.monotonic()+3
        while self.manager.active!=first['id'] and time.monotonic()<end:time.sleep(.01)
        second=self.manager.create('valid')
        self.manager.cancel(second['id'])
        self.assertEqual(self.manager.get(second['id'])['status'],'cancelled')
        self.manager.cancel(first['id'])
        for run in (first,second):
            final=self.terminal(run)
            self.assertEqual(final['status'],'cancelled')
            self.assertIsNone(final['audio_url'])
        self.assertFalse((self.manager._path(second['id'])/'output.wav').exists())

    def test_queue_bound_and_second_owner_read_only(self):
        self.manager.create('sleep')
        end=time.monotonic()+3
        while self.manager.active is None and time.monotonic()<end:time.sleep(.01)
        for i in range(3):self.manager.create('queued '+str(i))
        with self.assertRaisesRegex(InferenceError,'queue_full'):self.manager.create('fourth')
        other=Inference(self.home)
        try:
            with self.assertRaisesRegex(InferenceError,'operation_running'):other.create('other owner')
        finally:other.close()

    def test_restart_marks_pending_interrupted(self):
        self.manager.close()
        run_id='a'*32
        directory=self.home/'tts'/run_id;directory.mkdir()
        (directory/'state.json').write_text(json.dumps(dict(id=run_id,status='running',started_at='2026-01-01',metrics={})))
        self.manager=Inference(self.home)
        run=self.manager.get(run_id)
        self.assertEqual((run['status'],run['error']),('interrupted','process_interrupted'))

    def test_second_owner_cannot_fake_cancellation(self):
        first=self.manager.create('sleep')
        end=time.monotonic()+3
        while self.manager.active!=first['id'] and time.monotonic()<end:time.sleep(.01)
        other=Inference(self.home)
        try:
            with self.assertRaisesRegex(InferenceError,'operation_running'):other.cancel(first['id'])
        finally:other.close()

    def test_prepare_binds_current_exact_model_bytes_and_provenance(self):
        self.manager.close()
        self.manager=Inference(self.home)
        prep_id='b'*32
        assets=self.home/'preparations'/prep_id/'assets';assets.mkdir(parents=True)
        content=b'new synthetic model component for independent review'
        (assets/'config.json').write_bytes(content)
        model=dict(model_id='qwen3-tts-0.6b-customvoice',name='synthetic-test-model',revision='r1',source='https://example.invalid/official',files=[dict(path='config.json',size=len(content),sha256=hashlib.sha256(content).hexdigest())])
        (assets.parent.parent/'current.json').write_text(json.dumps(dict(id=prep_id,status='ready',integrity='matched')))
        runtime=self.home/'runtime';(runtime/'venv/Scripts').mkdir(parents=True)
        (runtime/'venv/Scripts/python.exe').write_bytes(b'not executed')
        (runtime/'environment.json').write_text(json.dumps(dict(status='ready')))
        run=dict(id='c'*32,text='이번 검증의 새 입력',input_sha256='d'*64,parameters={},model={'id':model['model_id'],'name':model['name'],'revision':model['revision']})
        self.manager._path(run['id']).mkdir()
        with patch('ai_manager.inference.manifest',return_value=model):
            self.manager._prepare(run)
            provenance=json.loads((self.manager._path(run['id'])/'provenance.json').read_text(encoding='utf8'))
            self.assertEqual(provenance['run_id'],run['id'])
            self.assertEqual(provenance['inputs'][0]['sha256'],model['files'][0]['sha256'])
            # A catalogue binding must prove both the registered source and prepared copy.
            registered=self.home/'registered-original';registered.mkdir();(registered/'config.json').write_bytes(content)
            from ai_manager.registry import sha
            from ai_manager.models import manifest_path
            run['registry_binding']=dict(id='e'*32,generation='f'*32,fingerprint='a'*64,
                manifest_sha256=hashlib.sha256(manifest_path(model['model_id']).read_bytes()).hexdigest(),
                asset_sha256=sha([{k:i[k] for k in ('path','size','sha256')} for i in model['files']]),registered_source=str(registered))
            self.manager._prepare(run)
            self.assertEqual(json.loads((self.manager._path(run['id'])/'provenance.json').read_text(encoding='utf8'))['registry_binding'],run['registry_binding'])
            (registered/'config.json').write_bytes(b'changed registered source')
            with self.assertRaisesRegex(InferenceError,'registered_artifact_mismatch'):self.manager._prepare(run)
            (registered/'config.json').write_bytes(content)
            (assets/'config.json').write_bytes(b'changed')
            with self.assertRaisesRegex(InferenceError,'model_integrity_failed'):self.manager._prepare(run)
            (assets/'config.json').write_bytes(content)
            (assets/'old-output.wav').write_bytes(b'forbidden previous output')
            with self.assertRaisesRegex(InferenceError,'model_integrity_failed'):self.manager._prepare(run)

    def test_retry_is_new_directory_and_input_not_old_audio(self):
        first=self.terminal(self.manager.create('valid'))
        second=self.terminal(self.manager.create('valid'))
        self.assertNotEqual(first['id'],second['id'])
        self.assertNotEqual(self.manager._path(first['id']),self.manager._path(second['id']))
        self.assertEqual(set(json.loads((self.manager._path(second['id'])/'input.json').read_text(encoding='utf8'))),{'text','sha256','parameters'})

    def test_cancel_during_output_validation_wins_over_late_success(self):
        entered,release=threading.Event(),threading.Event()
        original=validate_wav
        def blocked(path):
            entered.set();release.wait(3);return original(path)
        with patch('ai_manager.inference.validate_wav',side_effect=blocked):
            run=self.manager.create('valid')
            self.assertTrue(entered.wait(3))
            self.manager.cancel(run['id']);release.set()
            final=self.terminal(run)
        self.assertEqual(final['status'],'cancelled')
        self.assertIsNone(final['output'])
        with self.assertRaises(InferenceError):self.manager.audio(run['id'])

    @unittest.skipUnless(sys.platform=='win32','Windows job-object descendant audit')
    def test_worker_owned_descendant_is_killed_after_parent_exits(self):
        import ctypes
        from ctypes import wintypes
        run=self.terminal(self.manager.create('tree'))
        self.assertEqual(run['status'],'succeeded')
        pid=int((self.manager._path(run['id'])/'descendant.pid').read_text(encoding='utf8'))
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        kernel.OpenProcess.restype=wintypes.HANDLE
        kernel.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes=[wintypes.HANDLE]
        handle=kernel.OpenProcess(0x1000,False,pid)
        if handle:
            try:
                code=wintypes.DWORD();self.assertTrue(kernel.GetExitCodeProcess(handle,ctypes.byref(code)))
                self.assertNotEqual(code.value,259,'owned descendant is still active')
            finally:kernel.CloseHandle(handle)


class IndependentWavTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'fresh.wav'
    def tearDown(self):self.temp.cleanup()
    def write(self,values,rate=24000,channels=1,width=2):
        with wave.open(str(self.path),'wb') as w:
            w.setparams((channels,width,rate,0,'NONE','not compressed'))
            w.writeframes(struct.pack('<'+'h'*len(values),*values))
    def test_silence_truncated_bad_rate_channels_rejected(self):
        for values,rate,channels in [([0]*240,24000,1),([1]*240,8000,1),([1]*240,24000,2)]:
            self.write(values,rate,channels)
            with self.assertRaises(InferenceError):validate_wav(self.path)
        self.write([1]*240);self.path.write_bytes(self.path.read_bytes()[:-2])
        with self.assertRaises(InferenceError):validate_wav(self.path)
    def test_clipped_output_rejected(self):
        self.write([32767,-32768]*120)
        with self.assertRaisesRegex(InferenceError,'output_invalid'):validate_wav(self.path)
    def test_riff_size_and_trailing_bytes_rejected(self):
        self.write([100]*240)
        original=self.path.read_bytes()
        for raw in (original+b'extra old output',original[:4]+b'\xff\xff\xff\x7f'+original[8:]):
            self.path.write_bytes(raw)
            with self.assertRaisesRegex(InferenceError,'output_invalid'):validate_wav(self.path)


class IndependentPublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.directory=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def writer(self,fail=False,mismatch=False):
        directory=self.directory
        class Writer:
            def write(self,path,audio,rate,**kwargs):
                self.path=Path(path)
                assert self.path.name.endswith('.partial.wav')
                assert self.path.parent==directory
                self.path.write_bytes(b'fresh complete synthetic PCM payload')
                if fail:raise OSError('synthetic disk write interrupted')
            def info(self,path):
                assert Path(path)==self.path
                return SimpleNamespace(frames=4 if not mismatch else 3,samplerate=24000,channels=1,subtype='PCM_16')
        return Writer()
    def test_atomic_publication_removes_only_own_partial(self):
        from ai_manager.tts_worker import publish_audio
        sentinel=self.directory/'previous.partial.wav';sentinel.write_bytes(b'preserve')
        publish_audio(self.directory,SimpleNamespace(size=4),24000,self.writer())
        self.assertEqual((self.directory/'output.wav').read_bytes(),b'fresh complete synthetic PCM payload')
        self.assertEqual(sentinel.read_bytes(),b'preserve')
        self.assertEqual(list(self.directory.glob('*.partial.wav')),[sentinel])
    def test_no_overwrite_existing_output_preserved(self):
        from ai_manager.tts_worker import publish_audio
        (self.directory/'output.wav').write_bytes(b'existing output sentinel')
        with self.assertRaises(OSError):publish_audio(self.directory,SimpleNamespace(size=4),24000,self.writer())
        self.assertEqual((self.directory/'output.wav').read_bytes(),b'existing output sentinel')
        self.assertEqual(len(list(self.directory.glob('*.partial.wav'))),1)
    def test_interrupted_write_keeps_partial_and_no_final(self):
        from ai_manager.tts_worker import publish_audio
        with self.assertRaises(OSError):publish_audio(self.directory,SimpleNamespace(size=4),24000,self.writer(fail=True))
        self.assertFalse((self.directory/'output.wav').exists())
        self.assertEqual(len(list(self.directory.glob('*.partial.wav'))),1)
    def test_file_metadata_mismatch_never_published(self):
        from ai_manager.tts_worker import publish_audio
        with self.assertRaisesRegex(ValueError,'output_invalid'):publish_audio(self.directory,SimpleNamespace(size=4),24000,self.writer(mismatch=True))
        self.assertFalse((self.directory/'output.wav').exists())


class IndependentCompletionTests(unittest.TestCase):
    def inspect(self,tokens):
        from ai_manager.tts_worker import completion_metrics
        class Scalar:
            def __init__(self,value):self.value=value
            def all(self):return self
            def item(self):return self.value
        class Sequence:
            shape=(1,len(tokens))
            def __getitem__(self,key):return self
            def __eq__(self,other):return Scalar(tokens[-1]==other)
        class Torch:
            @staticmethod
            def stack(codes,dim):
                self.assertEqual(codes,[12,13,14]) # Hidden codes deliberately lack EOS 4198.
                return SimpleNamespace(shape=(1,3,16))
        value=SimpleNamespace(hidden_states=[(None,12),(None,13),(None,14)],sequences=Sequence())
        return completion_metrics(value,Torch,4198)
    def test_eos_only_in_final_sampled_sequence_is_complete(self):
        result=self.inspect([12,13,4198])
        self.assertTrue(result['eos_reached'])
        self.assertEqual((result['generated_codec_frames'],result['generated_sequence_tokens']),(3,3))
    def test_missing_final_eos_does_not_claim_complete(self):
        self.assertFalse(self.inspect([12,4198,13])['eos_reached'])
    def test_empty_sequence_does_not_claim_complete(self):
        self.assertFalse(self.inspect([])['eos_reached'])


class IndependentTtsHttpTests(unittest.TestCase):
    def setUp(self):
        from ai_manager.server import serve
        self.fixture=IndependentInferenceTests();self.fixture.setUp()
        self.ready=threading.Event();self.servers=[]
        def factory(*args,**kwargs):
            server=ThreadingHTTPServer(*args,**kwargs);self.servers.append(server);return server
        def browser(url):self.url=url.rstrip('/');self.ready.set()
        class Auth:
            class Store:
                def get(self,account):return None
            store=Store()
        self.server_patch=patch('ai_manager.server.ThreadingHTTPServer',factory)
        self.inference_patch=patch('ai_manager.server.Inference',return_value=self.fixture.manager)
        self.server_patch.start();self.inference_patch.start()
        self.thread=threading.Thread(target=serve,args=(self.fixture.home,{'allowlist':[]},Auth()),kwargs={'browser':browser},daemon=True)
        self.thread.start();self.assertTrue(self.ready.wait(3))
        self.csrf=requests.get(self.url+'/api/session',timeout=3).json()['csrf']
    def tearDown(self):
        self.servers[0].shutdown();self.thread.join(5)
        self.inference_patch.stop();self.server_patch.stop();self.fixture.tearDown()
    def post(self,path,data,**headers):
        return requests.post(self.url+path,data=json.dumps(data),headers={'Content-Type':'application/json','X-AiManager-CSRF':self.csrf,**headers},timeout=3)
    def test_csrf_origin_host_and_parameter_injection(self):
        for headers in [{'X-AiManager-CSRF':'wrong'},{'Origin':'https://foreign.invalid'},{'Host':'foreign.invalid'}]:
            self.assertEqual(self.post('/api/tts/runs',{'text':'fresh'},**headers).status_code,403)
        for data in [None,[],{}, {'text':''},{'text':'fresh','model_path':'../old-model'},{'text':'fresh','instruct':'execute'}]:
            self.assertEqual(self.post('/api/tts/runs',data).status_code,400)
        self.assertEqual(requests.get(self.url+'/api/tts/status',headers={'Origin':'https://foreign.invalid'},timeout=3).status_code,403)
    def test_audio_range_no_store_headers_and_exact_bytes(self):
        created=self.post('/api/tts/runs',{'text':'fresh synthetic audio'})
        self.assertEqual(created.status_code,202)
        run=self.fixture.terminal(created.json()['run'])
        path='/api/tts/runs/'+run['id']+'/audio'
        content=self.fixture.manager.audio(run['id'])
        response=requests.get(self.url+path,headers={'Range':'bytes=0-99'},timeout=3)
        self.assertEqual(response.status_code,200) # Full-body Range fallback is permitted.
        self.assertEqual(response.content,content)
        self.assertEqual(response.headers['Content-Type'],'audio/wav')
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        self.assertEqual(response.headers['X-Content-Type-Options'],'nosniff')
        self.assertNotIn('Access-Control-Allow-Origin',response.headers)
        download=requests.get(self.url+path+'?download=1',timeout=3)
        self.assertEqual(download.headers['Content-Disposition'],'attachment; filename="'+run['id']+'.wav"')
    def test_cancel_api_and_incomplete_audio_hidden(self):
        run=self.post('/api/tts/runs',{'text':'sleep'}).json()['run']
        path='/api/tts/runs/'+run['id']
        self.assertEqual(requests.get(self.url+path+'/audio',timeout=3).status_code,409)
        self.assertEqual(self.post(path+'/cancel',{}).status_code,202)
        self.assertEqual(self.fixture.terminal(run)['status'],'cancelled')
        self.assertEqual(requests.get(self.url+path+'/audio',timeout=3).status_code,409)
        self.assertEqual(requests.get(self.url+'/api/tts/runs/'+'e'*32+'/audio',timeout=3).status_code,404)


if __name__=='__main__':unittest.main()
