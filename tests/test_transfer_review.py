"""Independent adversarial range-transfer tests; new synthetic bytes only."""
import threading
import time
import unittest
import requests
from ai_manager.drive import Drive, DriveError, Cancelled

BLOCK=1024*1024
FULL_SIZE=8*BLOCK+13
class Response:
    def __init__(self, session, start, end, size):
        self.session,self.start,self.end=session,start,end
        self.status_code=200 if session.mode=='200' else 206
        self.headers={'Content-Range':f'bytes {start}-{end}/{size}'}
        if session.mode=='wrong_start':self.headers['Content-Range']=f'bytes {start+1}-{end}/{size}'
        if session.mode=='wrong_total':self.headers['Content-Range']=f'bytes {start}-{end}/{size+1}'
        if session.mode=='missing_range':self.headers={}
    def __enter__(self):
        with self.session.guard:
            self.session.active+=1;self.session.peak=max(self.session.peak,self.session.active)
        return self
    def __exit__(self,*args):
        with self.session.guard:self.session.active-=1;self.session.closed+=1
    def iter_content(self,chunk_size):
        if self.session.mode=='cancel':self.session.cancel.set()
        if self.session.mode=='failure' and self.start==BLOCK:
            raise requests.ConnectionError('synthetic-sensitive-url-and-token')
        if self.session.mode=='failure':time.sleep(.08)
        length=self.end-self.start+1
        if self.session.mode=='short':length-=1
        if self.session.mode=='long':length+=1
        block=bytes([self.start//BLOCK%251])
        for offset in range(0,length,chunk_size):yield block*min(chunk_size,length-offset)

class Session:
    def __init__(self,mode='ok',cancel=None):
        self.mode=mode;self.cancel=cancel or threading.Event();self.calls=[];self.active=0;self.peak=0;self.closed=0;self.guard=threading.Lock()
    def get(self,url,**kwargs):
        text=kwargs['headers']['Range'].removeprefix('bytes=');start,end=map(int,text.split('-'))
        with self.guard:self.calls.append((start,end,kwargs))
        return Response(self,start,end,self.size)

class RangeReviewTests(unittest.TestCase):
    def setup_drive(self,mode='ok',size=FULL_SIZE):
        cancel=threading.Event();session=Session(mode,cancel);session.size=size
        return Drive('synthetic-bearer',session=session,cancel=cancel),session
    def test_range_bytes_are_ordered_bounded_and_closed(self):
        drive,s=self.setup_drive(size=FULL_SIZE);parts=list(drive.content('synthetic-file',s.size))
        self.assertEqual([len(p) for p in parts],[BLOCK]*8+[13]);self.assertEqual([p[0] for p in parts],list(range(9)))
        self.assertLessEqual(s.peak,8);self.assertEqual(s.active,0);self.assertEqual(s.closed,len(s.calls))
        for _,_,kwargs in s.calls:
            self.assertFalse(kwargs['allow_redirects']);self.assertEqual(kwargs['headers']['Accept-Encoding'],'identity')
    def test_200_or_malformed_content_range_rejected(self):
        for mode in ('200','wrong_start','wrong_total','missing_range'):
            with self.subTest(mode=mode):
                drive,s=self.setup_drive(mode)
                with self.assertRaisesRegex(DriveError,'^download_invalid_range$'):list(drive.content('synthetic-file',s.size))
                self.assertEqual(s.active,0);self.assertEqual(s.closed,len(s.calls))
    def test_short_and_overlong_range_rejected(self):
        for mode in ('short','long'):
            with self.subTest(mode=mode):
                drive,s=self.setup_drive(mode)
                with self.assertRaisesRegex(DriveError,'^download_invalid_range$'):list(drive.content('synthetic-file',s.size))
                self.assertEqual(s.active,0)
    def test_middle_failure_sanitized_and_workers_joined(self):
        drive,s=self.setup_drive('failure')
        with self.assertRaisesRegex(DriveError,'^download_network_interrupted$'):list(drive.content('synthetic-file',s.size))
        self.assertEqual(s.active,0);self.assertEqual(s.closed,len(s.calls))
    def test_cancellation_closes_all_worker_responses(self):
        drive,s=self.setup_drive('cancel')
        with self.assertRaises(Cancelled):list(drive.content('synthetic-file',s.size))
        self.assertEqual(s.active,0);self.assertEqual(s.closed,len(s.calls))
    def test_parallel_transfer_does_not_race_account_access(self):
        drive,s=self.setup_drive();guard=threading.Lock()
        def access():
            if not guard.acquire(False):raise RuntimeError('account_operation_busy')
            try:time.sleep(.02);return 'synthetic-bearer'
            finally:guard.release()
        drive.access=access
        parts=list(drive.content('synthetic-file',s.size))
        self.assertEqual(sum(map(len,parts)),s.size)
    def test_simultaneous_401_refreshes_once_and_reuses_new_token(self):
        drive,s=self.setup_drive();barrier=threading.Barrier(8);original=s.get;calls={'initial':0,'refresh':0}
        def access(force_refresh=False):
            calls['refresh' if force_refresh else 'initial']+=1
            return 'new-synthetic-token' if force_refresh else 'old-synthetic-token'
        def get(url,**kwargs):
            result=original(url,**kwargs)
            if kwargs['headers']['Authorization']=='Bearer old-synthetic-token':
                barrier.wait(timeout=5);result.status_code=401
            return result
        drive.access=access;s.get=get
        self.assertEqual(sum(map(len,drive.content('synthetic-file',s.size))),s.size)
        self.assertEqual(calls,{'initial':1,'refresh':1});self.assertEqual(s.active,0)
    def test_refresh_failure_is_sanitized_and_workers_join(self):
        drive,s=self.setup_drive();original=s.get
        def access(force_refresh=False):
            if force_refresh:raise ValueError('synthetic-secret-must-not-leak')
            return 'synthetic-expired-token'
        def get(url,**kwargs):
            result=original(url,**kwargs);result.status_code=401;return result
        drive.access=access;s.get=get
        with self.assertRaisesRegex(DriveError,'^authentication_refresh_failed$'):list(drive.content('synthetic-file',s.size))
        self.assertEqual(s.active,0);self.assertEqual(s.closed,len(s.calls))
    def test_429_ranges_backoff_and_recover(self):
        drive,s=self.setup_drive();original=s.get;attempts={};waits=[];guard=threading.Lock()
        def get(url,**kwargs):
            result=original(url,**kwargs);key=kwargs['headers']['Range']
            with guard:attempts[key]=attempts.get(key,0)+1;first=attempts[key]==1
            if first:result.status_code=429
            return result
        s.get=get;drive._wait=waits.append
        self.assertEqual(sum(map(len,drive.content('synthetic-file',s.size))),s.size)
        self.assertEqual(len(waits),9);self.assertEqual(s.active,0)
    def test_cancellation_during_range_backoff_stops_workers(self):
        drive,s=self.setup_drive();original=s.get
        def get(url,**kwargs):result=original(url,**kwargs);result.status_code=429;return result
        def wait(attempt):s.cancel.set();Drive._wait(drive,attempt)
        s.get=get;drive._wait=wait
        with self.assertRaises(Cancelled):list(drive.content('synthetic-file',s.size))
        self.assertEqual(s.active,0)
    def test_consumer_close_joins_workers(self):
        drive,s=self.setup_drive();stream=drive.content('synthetic-file',s.size);next(stream);stream.close()
        self.assertEqual(s.active,0);self.assertEqual(s.closed,len(s.calls))

class PreparationRangeIntegrationTests(unittest.TestCase):
    def test_range_full_hash_and_atomic_publication(self):
        self.check_preparation('ok')
    def test_failed_range_never_publishes_model(self):
        self.check_preparation('failure')
    def check_preparation(self,mode):
        import hashlib
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from ai_manager.preparation import Preparation,MODEL_SEGMENT
        from test_preparation_review import FakeDrive,MANIFEST,PAYLOAD
        size=FULL_SIZE;session=Session(mode);session.size=size
        ranged=Drive('synthetic-bearer',session=session,cancel=session.cancel)
        fake=FakeDrive(cancel=session.cancel);fake.items['weight'].update(size=str(size))
        digest=hashlib.sha256(b''.join(bytes([i])*BLOCK for i in range(8))+b'\10'*13).hexdigest()
        fake.items['weight']['sha256Checksum']=digest
        files=[dict(MANIFEST['files'][0]),dict(path='speech_tokenizer/model.safetensors',size=size,sha256=digest)]
        m=dict(MANIFEST,files=files)
        def content(fid,size=None):
            if fid=='weight':yield from ranged.content(fid,FULL_SIZE)
            else:yield PAYLOAD
        fake.content=content
        with tempfile.TemporaryDirectory() as folder:
            prep=Preparation(Path(folder),{'allowlist':[{'account':'B','id':'root'}]},object(),lambda *a,**kw:fake)
            observed=[{'path':'B_ROOT/'+MODEL_SEGMENT+'/config.json','metadata':fake.items['config']}]
            with patch('ai_manager.preparation.manifest',return_value=m),patch.object(prep,'_observed',return_value=observed):state=prep.prepare(session.cancel)
            target=prep.base/state['id']/'assets'/'speech_tokenizer'/'model.safetensors'
            self.assertEqual(session.active,0);self.assertEqual(session.closed,len(session.calls))
            if mode=='ok':
                self.assertEqual(state['status'],'ready');self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(),digest)
            else:self.assertEqual(state['status'],'failed');self.assertFalse(target.exists())

class WheelReviewTests(unittest.TestCase):
    def exercise(self,mode):
        import hashlib
        import importlib.util
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        spec=importlib.util.spec_from_file_location('review_wheel',Path(__file__).parents[1]/'scripts'/'download_runtime_wheel.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        payload=b'new independent wheel transfer bytes';sha=hashlib.sha256(payload).hexdigest()
        class Reply:
            status_code=206
            headers={'Content-Range':f'bytes 0-{len(payload)-1}/{len(payload)}','ETag':'"synthetic-etag"','Content-Length':str(len(payload))}
            text=f'<a href="https://download.pytorch.org/whl/cu128/{module.FILENAME}#sha256={sha}">wheel</a>'
            def raise_for_status(self):pass
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def iter_content(self,size):yield payload if mode!='hash' else b'x'*len(payload)
        def get(url,**kwargs):
            reply=Reply();reply.headers=dict(Reply.headers)
            if 'headers' in kwargs:
                self.assertEqual(kwargs['headers']['If-Range'],'"synthetic-etag"')
                if mode=='etag':reply.headers['ETag']='"changed"'
                if mode=='200':reply.status_code=200
            return reply
        with tempfile.TemporaryDirectory() as folder,patch.dict('os.environ',{'LOCALAPPDATA':folder}),patch.object(module.requests,'get',side_effect=get),patch.object(module.requests,'head',return_value=Reply()):
            if mode=='ok':
                import contextlib,io
                with contextlib.redirect_stdout(io.StringIO()):module.download()
                targets=list(Path(folder).rglob('*.whl'));self.assertEqual(len(targets),1);self.assertEqual(hashlib.sha256(targets[0].read_bytes()).hexdigest(),sha)
            else:
                with self.assertRaises(RuntimeError):module.download()
                self.assertFalse(list(Path(folder).rglob('*.whl')))
    def test_official_index_hash_and_range_etag(self):self.exercise('ok')
    def test_changed_wheel_etag_blocks_publication(self):self.exercise('etag')
    def test_ignored_wheel_range_blocks_publication(self):self.exercise('200')
    def test_wheel_hash_mismatch_blocks_publication(self):self.exercise('hash')

if __name__=='__main__':unittest.main()
