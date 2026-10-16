"""Fresh synthetic process recovery, independent of actual model inference."""
import json,os,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from ai_manager.inference import Inference
from ai_manager.inventory import _alive

CONTROLLER = r'''
import json,sys,time
from pathlib import Path
from ai_manager.inference import Inference
root=Path(sys.argv[1]);worker=root/'fresh_worker.py'
worker.write_text("import os,sys,time\\nfrom pathlib import Path\\nPath(sys.argv[1]).parent.joinpath('worker-started.json').write_text(str(os.getpid()))\\ntime.sleep(120)\\n".replace('\\n','\n'))
manager=Inference(root)
def prepare(run):
 directory=manager._path(run['id']);(directory/'request.json').write_text(json.dumps(run))
 return Path(getattr(sys,'_base_executable',sys.executable)),worker
manager._prepare=prepare
first=manager.create('M6 new synthetic interrupted input')
end=time.monotonic()+10
while time.monotonic()<end:
 marker=manager._path(first['id'])/'worker-started.json'
 if marker.exists():break
 time.sleep(.02)
else:raise RuntimeError('fresh worker not started')
second=manager.create('M6 new synthetic queued input')
(root/'ready.json').write_text(json.dumps({'active':first['id'],'queued':second['id'],'worker_pid':int(marker.read_text())}))
while True:time.sleep(.1)
'''

class M6ProcessRecoveryTests(unittest.TestCase):
    @unittest.skipUnless(os.name=='nt','Windows job-object test')
    def test_owned_controller_crash_kills_worker_and_restart_interrupts_runs(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            process=subprocess.Popen([sys.executable,'-c',CONTROLLER,str(root)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                end=time.monotonic()+12
                while time.monotonic()<end and not (root/'ready.json').exists() and process.poll() is None:time.sleep(.02)
                if not (root/'ready.json').exists():self.fail('controller failed: '+process.communicate(timeout=2)[1].decode(errors='replace'))
                info=json.loads((root/'ready.json').read_text());self.assertTrue(_alive(info['worker_pid']))
                process.terminate();process.wait(timeout=5)
                end=time.monotonic()+5
                while time.monotonic()<end and _alive(info['worker_pid']):time.sleep(.02)
                self.assertFalse(_alive(info['worker_pid']))
                recovered=Inference(root)
                try:
                    for key in ('active','queued'):
                        run=recovered.get(info[key]);self.assertEqual((run['status'],run['error']),('interrupted','process_interrupted'));self.assertIsNone(run['audio_url'])
                        self.assertFalse((root/'tts'/info[key]/'output.wav').exists())
                    self.assertTrue(recovered.owner.handle)
                finally:recovered.close()
            finally:
                if process.poll() is None:process.terminate();process.wait(timeout=5)
                process.communicate(timeout=2)
