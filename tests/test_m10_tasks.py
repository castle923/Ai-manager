"""Fresh synthetic contract fixtures; no model/OAuth/GPU or historical result reuse."""
import base64
import io
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
import wave
from unittest.mock import patch

import requests
from ai_manager import adapters,task_contracts,task_runtime
from ai_manager.desktop_files import save_task_output
from ai_manager.execution_slot import acquire
from ai_manager.history import History
from ai_manager.server import create_application
from ai_manager.task_inference import TaskInference


def audio():
    value=io.BytesIO()
    with wave.open(value,'wb') as stream:
        stream.setparams((1,2,16000,0,'NONE','not compressed'))
        stream.writeframes(b'\x10\x01\xf0\xfe'*800)
    return value.getvalue()


class Contracts(unittest.TestCase):
    def test_input_is_bounded_decoded_audio_not_a_path(self):
        data=audio();info=task_contracts.wav_input(data)
        self.assertEqual(info['duration_seconds'],.1)
        self.assertEqual(task_contracts.decode_input({'audio_base64':base64.b64encode(data).decode()})[0],data)
        for payload in ({'path':'source.wav'},{'audio_base64':'not base64'},{'audio_base64':'A'*1_281_001}):
            with self.assertRaises(ValueError):task_contracts.decode_input(payload)
        with self.assertRaises(ValueError):task_contracts.wav_input(data[:-1])

    def test_types_without_complete_worker_and_manifest_never_ready(self):
        with tempfile.TemporaryDirectory() as tmp:
            items=adapters.catalog(Path(tmp))
        self.assertEqual(len(items),4)
        self.assertTrue(all(not i['execution_verified'] for i in items))
        for item in items:
            self.assertEqual(item['runtime']['status'],'unverified')
            if item['configuration']!='manifest_available':self.assertFalse(item['implementation_available'])

    def test_outputs_have_content_and_hash_contract_not_filename_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);value=dict(text='이번 새 테스트 전사',language='ko',input_duration_seconds=.1,timestamps=None)
            (root/'transcript.json').write_text(json.dumps(value,ensure_ascii=False),'utf8')
            (root/'transcript.txt').write_text(value['text'],'utf8')
            data,meta=task_contracts.output(root,'text',root)
            self.assertEqual(meta['sha256'],task_contracts.sha(data))
            with self.assertRaises(ValueError):task_contracts.output(root,'../input',root)
            (root/'transcript.txt').write_text('변조','utf8')
            with self.assertRaises(ValueError):task_contracts.output(root,'text',root)

    def test_native_export_requires_exact_artifact_new_path_and_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);data=b'new transcript';meta=dict(id='text',filename='transcript.txt',extension='.txt',mime='text/plain; charset=utf-8',bytes=len(data),sha256=task_contracts.sha(data))
            class Tasks:
                owner=type('Owner',(),{'handle':True})();closed=threading.Event()
                def export(self,run,output):
                    if output!='text':raise ValueError('output_not_found')
                    return data,meta
            task=Tasks();target=root/'fresh.txt'
            self.assertEqual(save_task_output(task,'a'*32,'text',target)['sha256'],meta['sha256'])
            self.assertEqual(target.read_bytes(),data)
            with self.assertRaises(ValueError):save_task_output(task,'a'*32,'text',target)
            with self.assertRaises(ValueError):save_task_output(task,'a'*32,'text',root/'wrong.png')

    def test_slot_wait_can_cancel_and_reacquire_without_foreign_process_control(self):
        with tempfile.TemporaryDirectory() as tmp:
            stop=threading.Event();first=acquire(Path(tmp),lambda:None,stop);cancel=threading.Event();result=[]
            def wait():
                def check():
                    if cancel.is_set():raise ValueError('cancelled')
                try:acquire(Path(tmp),check,stop)
                except ValueError as error:result.append(str(error))
            thread=threading.Thread(target=wait);thread.start();time.sleep(.2);cancel.set();thread.join(2)
            self.assertEqual(result,['cancelled']);first.close()
            acquire(Path(tmp),lambda:None,stop).close()

    def test_corrupt_records_are_isolated_from_status_and_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp);directory=home/'task-runs'/('a'*32);directory.mkdir(parents=True);(directory/'state.json').write_text('[]')
            tasks=TaskInference(home)
            try:self.assertEqual(tasks.snapshot()['runs'],[])
            finally:tasks.close()
            directory=task_runtime.root(home,'whisper-large-v3-turbo');directory.mkdir(parents=True);(directory/'environment.json').write_text('[]')
            self.assertEqual(task_runtime.environment(home,'whisper-large-v3-turbo')['status'],'unverified')
            source=home/'task-runs'/('a'*32)/'state.json';source.write_text(json.dumps(dict(id='a'*32,status='failed',started_at='2026-10-18T01:00:00+00:00',input=[1],metrics={})))
            result=History(home).query({})
            self.assertTrue(any(item['read_error'] for item in result['items']))


class Http(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        class Auth:
            class Store:
                def get(self,account):return None
            store=Store()
        self.app=create_application(Path(self.temp.name),{'allowlist':[]},Auth());self.url=self.app.start().rstrip('/')
        self.csrf=requests.get(self.url+'/api/session',timeout=5).json()['csrf']

    def tearDown(self):self.app.close();self.temp.cleanup()

    def test_security_and_unknown_output_do_not_leak_source(self):
        status=requests.get(self.url+'/api/tasks/status',timeout=5)
        self.assertEqual(status.status_code,200);self.assertEqual(status.json()['runs'],[])
        for headers in ({'Origin':'https://foreign.invalid'},{'Host':'foreign.invalid'}):
            self.assertEqual(requests.get(self.url+'/api/tasks/status',headers=headers,timeout=5).status_code,403)
        endpoint='/api/tasks/runs/'+'a'*32+'/cancel'
        self.assertEqual(requests.post(self.url+endpoint,json={},timeout=5).status_code,403)
        response=requests.post(self.url+endpoint,json={},headers={'X-AiManager-CSRF':self.csrf},timeout=5)
        self.assertEqual(response.json()['error'],'run_not_found')
        self.assertEqual(requests.get(self.url+'/api/tasks/runs/'+'a'*32+'/outputs/../../source',timeout=5).status_code,404)

if __name__=='__main__':unittest.main()
