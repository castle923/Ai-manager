"""Independent psutil-state / Popen-exit visibility; no real process starts."""
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('exit_confirmation_guard', Path(__file__).parent.parent/'scripts/colab/llama_watchdog.py')
m = importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class ExitConfirmationTests(unittest.TestCase):
    def run_fake(self, mode='zombie', *, pressure=None, descendant=False, deadline=False, log_error=None, pre_gate=False):
        temporary = tempfile.TemporaryDirectory(prefix='guard-independent-exit-')
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name);clock = [0.];events = [];signals = [];rss_reused=[False]
        class Missing(Exception):pass
        class Denied(Exception):pass
        class Process:
            pid = 100
            returncode = None
            stdout = io.BytesIO()
            stderr = io.BytesIO()
            def poll(self):
                if mode=='zombie_poll_overrun' and clock[0]>=.04:
                    clock[0]=1.03
                exit_at=1.02 if mode=='zombie_boundary' else .08
                if self.returncode is None and (root/'start.gate').exists() and clock[0]>=exit_at and mode not in ('zombie_forever','absent_forever'):
                    self.returncode=9 if mode=='zombie_nonzero' else 0
                events.append(('poll',clock[0],self.returncode));return self.returncode
            def wait(self,timeout=None):
                if self.returncode is None:self.returncode=0
                events.append(('wait',clock[0],self.returncode));return self.returncode
        process = Process()
        class Observed:
            def __init__(self,pid):self.pid=pid
            def create_time(self):
                if self.pid==200:return 2.
                if (mode in ('reuse','zombie_reused') and clock[0]>=.02
                        or mode=='zombie_then_reuse' and clock[0]>=.04 or rss_reused[0]):return 999.
                return 1.
            def is_running(self):
                if self.pid==200:return fake.descendant
                if mode in ('absent','absent_forever') and clock[0]>=.02:raise Missing()
                return not (mode=='unknown_live' and clock[0]>=.02) and process.returncode is None
            def status(self):
                if self.pid==100 and mode in ('absent','absent_forever') and clock[0]>=.02:raise Missing()
                zombie=(mode in ('zombie','zombie_forever','zombie_nonzero','zombie_reused','zombie_boundary','zombie_poll_overrun','zombie_rss_reused')
                        or mode in ('zombie_then_live','zombie_then_reuse') and clock[0]<.04)
                state='zombie' if self.pid==100 and clock[0]>=.02 and zombie else 'running'
                events.append(('state',clock[0],state));return state
            def children(self,recursive=False):return [Observed(200)] if self.pid==100 and fake.descendant else []
            def memory_info(self):
                if pressure=='RSS_error' and clock[0]>=.02:raise Denied('private-measurement-error')
                if mode=='zombie_rss_reused' and clock[0]>=.02:rss_reused[0]=True
                return type('Memory',(),{'rss':8*m.GiB if pressure=='RSS' and clock[0]>=.04 else 128*1024**2})()
            def terminate(self):
                signals.append(self.pid)
                if self.pid==200:fake.descendant=False
                else:process.returncode=-15
            kill=terminate
        class FakePsutil:
            STATUS_ZOMBIE='zombie'
            NoSuchProcess=Missing
            AccessDenied=Denied
            Process=Observed
        fake=FakePsutil();fake.descendant=descendant
        backend=m.PsutilBackend.__new__(m.PsutilBackend);backend.psutil=fake
        class ImmediateThread:
            def __init__(self,target,args,**kwargs):self.target,self.args=target,args
            def start(self):self.target(*self.args)
            def join(self,timeout=None):pass
            def is_alive(self):return False
        event_count=[0]
        class FakeEvent:
            def __init__(self):self.index=event_count[0];event_count[0]+=1;self.flag=False
            def set(self):self.flag=True
            def is_set(self):return self.flag or clock[0]>=.04 and self.index==({'reader':0,'overflow':1}.get(log_error,-1))
        def launch(*args,**kwargs):
            if not pre_gate:
                (root/'handshake.json').write_text(json.dumps(dict(pid=100,create_time=1.,baseline_rss_bytes=128*1024**2,incremental_budget_bytes=m.GiB)))
            return process
        def sample():
            return dict(available_bytes=m.GiB if pressure=='OS' and clock[0]>=.04 else 10*m.GiB,
                        cgroup_headroom_bytes=m.GiB if pressure=='cgroup' and clock[0]>=.04 else 10*m.GiB)
        def sleep(seconds):clock[0]+=seconds
        with patch.object(m.subprocess,'Popen',side_effect=launch),patch.object(m.threading,'Thread',ImmediateThread), \
             patch.object(m.threading,'Event',FakeEvent),patch.object(m.time,'monotonic',side_effect=lambda:clock[0]),patch.object(m.time,'sleep',side_effect=sleep):
            result=m.run_owned(['synthetic-no-launch'],root,{},_backend=backend,_sample=sample,
                interval_seconds=.02,terminate_grace_seconds=0,timeout_seconds=.06 if deadline else 600,
                handshake_seconds=.06 if deadline or pre_gate else 120)
        return result,events,signals

    def test_owned_zombie_wait_visibility_lag_confirms_exact_popen_exit(self):
        result,events,signals=self.run_fake('zombie')
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['worker_returncode'],0)
        self.assertEqual(result['final_worker_returncode'],0)
        self.assertIn(('state',.02,'zombie'),events)
        self.assertIn(('poll',.02,None),events)
        self.assertEqual(signals,[])
        self.assertEqual(result['identity_observation'],'owned_zombie')
        self.assertEqual(result['exit_poll_path'],'main_poll')
        self.assertGreater(result['exit_confirmation_samples'],0)
        self.assertEqual(result['peak_owned_RSS_bytes'],128*1024**2)

    def test_missing_process_wait_visibility_lag_confirms_exact_popen_exit(self):
        result,_,signals=self.run_fake('absent')
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['worker_returncode'],0)
        self.assertEqual(signals,[])
        self.assertEqual(result['identity_observation'],'process_absent')

    def test_unknown_live_and_changed_live_identity_still_fail_closed(self):
        for mode in ('unknown_live','reuse','zombie_reused'):
            with self.subTest(mode=mode):
                result,_,signals=self.run_fake(mode)
                self.assertEqual(result['primary_reason'],'worker_identity_changed')
                self.assertEqual(result['status'],'stopped')
                self.assertNotIn('worker_returncode',result)
                self.assertEqual(signals,[])

    def test_confirmation_timeout_never_uses_final_wait_zero_as_success(self):
        for mode in ('zombie_forever','absent_forever'):
            with self.subTest(mode=mode):
                result,_,signals=self.run_fake(mode)
                self.assertEqual(result['primary_reason'],'worker_exit_confirmation_timeout')
                self.assertEqual(result['status'],'stopped')
                self.assertNotIn('worker_returncode',result)
                self.assertEqual(result['final_worker_returncode'],0)
                self.assertLessEqual(result['elapsed_seconds'],1.1)
                self.assertEqual(signals,[])

    def test_memory_rss_and_deadline_remain_active_while_confirming_exit(self):
        for pressure,reason in (('OS','OS_memory_floor'),('cgroup','cgroup_memory_floor'),('RSS','RSS_cap')):
            with self.subTest(pressure=pressure):
                result,_,_=self.run_fake(pressure=pressure,descendant=pressure=='RSS')
                self.assertEqual(result['primary_reason'],reason)
                self.assertEqual(result['status'],'stopped')
        result,_,_=self.run_fake(deadline=True)
        self.assertEqual(result['primary_reason'],'deadline_exceeded')

    def test_known_descendant_blocks_completed_exit(self):
        result,_,signals=self.run_fake(descendant=True)
        self.assertEqual(result['primary_reason'],'owned_descendant_survived')
        self.assertEqual(result['status'],'stopped')
        self.assertEqual(signals,[200])

    def test_pending_exit_rechecks_live_or_reused_identity_each_iteration(self):
        for mode in ('zombie_then_live','zombie_then_reuse'):
            with self.subTest(mode=mode):
                result,_,signals=self.run_fake(mode)
                self.assertEqual(result['primary_reason'],'worker_identity_changed')
                self.assertEqual(result['status'],'stopped')
                self.assertNotIn('worker_returncode',result)
                # Same owned live process may be stopped; a reused identity never is.
                self.assertEqual(signals,[] if mode=='zombie_then_reuse' else [100])

    def test_nonzero_confirmed_exit_never_passes(self):
        result,_,_=self.run_fake('zombie_nonzero')
        self.assertEqual(result['status'],'stopped')
        self.assertEqual(result['worker_returncode'],9)
        self.assertEqual(result['final_worker_returncode'],9)

    def test_log_guards_remain_active_during_exit_confirmation(self):
        for error,reason in (('reader','log_monitor_error'),('overflow','log_size_cap')):
            with self.subTest(error=error):
                result,_,_=self.run_fake(log_error=error)
                self.assertEqual(result['primary_reason'],reason)
                self.assertEqual(result['status'],'stopped')

    def test_pre_gate_confirmation_keeps_handshake_deadline_and_never_passes(self):
        result,_,_=self.run_fake('zombie_forever',pre_gate=True)
        self.assertFalse(result['gate_opened'])
        self.assertEqual(result['status'],'stopped')
        self.assertEqual(result['primary_reason'],'handshake_deadline_exceeded')

    def test_exit_state_permission_failure_is_only_a_fixed_unknown_enum(self):
        class Missing(Exception):pass
        class Denied(Exception):pass
        def inaccessible(pid):raise Denied('private-error-text')
        backend=m.PsutilBackend.__new__(m.PsutilBackend)
        backend.psutil=type('Fake',(),dict(Process=staticmethod(inaccessible),NoSuchProcess=Missing,AccessDenied=Denied))
        self.assertEqual(backend.exit_state(100,1.),'identity_unavailable')

    def test_exit_first_visible_at_confirmation_deadline_never_passes(self):
        for mode in ('zombie_boundary','zombie_poll_overrun'):
            with self.subTest(mode=mode):
                result,_,_=self.run_fake(mode)
                self.assertEqual(result['primary_reason'],'worker_exit_confirmation_timeout')
                self.assertEqual(result['status'],'stopped')
                self.assertNotIn('worker_returncode',result)
                self.assertEqual(result['final_worker_returncode'],0)

    def test_owned_zombie_root_rss_cap_is_enforced_without_descendants(self):
        result,_,signals=self.run_fake(pressure='RSS',descendant=False)
        self.assertEqual(result['primary_reason'],'RSS_cap')
        self.assertEqual(result['status'],'stopped')
        self.assertGreaterEqual(result['peak_owned_RSS_bytes'],result['RSS_cap_bytes'])
        self.assertEqual(signals,[])

    def test_zombie_rss_measurement_failure_or_identity_change_never_passes(self):
        result,_,signals=self.run_fake(pressure='RSS_error')
        self.assertEqual(result['primary_reason'],'monitor_error')
        self.assertEqual(result['status'],'stopped')
        self.assertEqual(signals,[])
        result,_,signals=self.run_fake('zombie_rss_reused')
        self.assertEqual(result['primary_reason'],'worker_identity_changed')
        self.assertEqual(result['status'],'stopped')
        self.assertEqual(signals,[])

    def test_zombie_root_rss_and_known_child_are_counted_once_each(self):
        result,_,_=self.run_fake(descendant=True)
        self.assertEqual(result['peak_owned_RSS_bytes'],256*1024**2)


if __name__=='__main__':unittest.main(verbosity=2)
