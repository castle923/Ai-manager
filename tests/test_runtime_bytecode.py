"""Protect original bundled pyc bytes at the actual subprocess boundaries."""
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock,patch

from ai_manager.task_runtime import RuntimeSetup
from ai_manager.task_inference import TaskInference


class BytecodeBoundary(unittest.TestCase):
    def test_every_runtime_python_call_disables_bytecode_even_when_isolated(self):
        process=Mock(returncode=0);process.poll.return_value=0
        child=Mock()
        with tempfile.TemporaryDirectory() as temporary:
            setup=RuntimeSetup(Path(temporary),Path(temporary)/'base/python.exe')
            with patch('ai_manager.external_process.spawn_external',return_value=process) as spawn,patch('ai_manager.inference.OwnedChild',return_value=child):
                for arguments in (['python.exe','-I','-m','venv','new'],['python.exe','-I','-m','pip','check'],['python.exe','-I','-c','print(1)']):
                    setup._run(arguments,None)
                    self.assertEqual(spawn.call_args.args[0],['python.exe','-B',*arguments[1:]])
            self.assertEqual(child.stop.call_count,3)
            self.assertEqual(child.close.call_count,3)

    def test_all_typed_worker_spawns_disable_bytecode(self):
        with tempfile.TemporaryDirectory() as temporary:
            for index,kind in enumerate(('stt','tracking','llm','image')):
                with self.subTest(kind=kind):
                    directory=Path(temporary)/kind;directory.mkdir()
                    tasks=TaskInference.__new__(TaskInference)
                    tasks.home=Path(temporary);tasks.lock=threading.RLock();tasks.closed=threading.Event();tasks.cancelled=set();tasks.popen=None;tasks.timeout=1
                    tasks._path=lambda identifier:directory
                    tasks._check=lambda identifier:None
                    tasks._save=lambda run:None
                    tasks._prepare=lambda run:(Path('python.exe'),Path(kind+'_worker.py'))
                    run=dict(id=str(index)*32,task_type=kind,input={'sha256':'0'*64},metrics={},outputs=[])
                    slot=Mock()
                    with patch('ai_manager.execution_slot.acquire',return_value=slot),patch('ai_manager.external_process.spawn_external',side_effect=RuntimeError('fixture stopped before any child')) as spawn:
                        tasks._execute(run)
                    self.assertEqual(spawn.call_args.args[0][:3],['python.exe','-I','-B'])
                    self.assertEqual(run['status'],'failed')
                    slot.close.assert_called_once()

if __name__=='__main__':unittest.main()
