"""Synthetic ownership/guard tests: no model, auth, network, or D access.

Production requires psutil in the Colab runtime. This development environment
does not have it installed, so tests inject a process adapter wrapping only
the actual Popen object created by the watchdog. No package installation.
"""
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).parent
TEST_PYTHON = getattr(sys, '_base_executable', sys.executable)
spec = importlib.util.spec_from_file_location('llama_watchdog', HERE.parent/'scripts/colab/llama_watchdog.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

WORKER = r'''
import argparse,json,os,pathlib,time,sys
p=argparse.ArgumentParser();p.add_argument('mode');p.add_argument('--watchdog-handshake');p.add_argument('--watchdog-gate');a=p.parse_args()
h=pathlib.Path(a.watchdog_handshake);g=pathlib.Path(a.watchdog_gate)
if a.mode=='nohandshake':time.sleep(10);sys.exit(0)
data=dict(pid=os.getpid(),create_time=123456.0,baseline_rss_bytes=134217728,incremental_budget_bytes=1073741824)
if a.mode=='badpid':data['pid']+=1
with h.open('x') as f:json.dump(data,f)
while not g.exists():time.sleep(.01)
pathlib.Path('loaded.marker').write_text('synthetic only')
if a.mode=='overflow':sys.stdout.write('x'*6000);sys.stdout.flush();time.sleep(10)
if a.mode=='timeout':time.sleep(10)
'''


class OwnedBackend:
    def __init__(self, root, high=False, change_identity=False):
        self.root = root
        self.process = None
        self.high = high
        self.change_identity = change_identity
        self.signals = []

    def identity(self, pid):
        if self.process is None or pid != self.process.pid or self.process.poll() is not None:
            return None
        if self.change_identity and (self.root/'handshake.json').exists():
            return 654321.0
        return 123456.0

    def children(self, pid):
        return []

    def rss(self, pid):
        return 8*m.GiB if self.high and (self.root/'start.gate').exists() else 128*1024**2

    def terminate(self, pid):
        assert pid == self.process.pid
        self.signals.append(('terminate', pid))
        self.process.terminate()

    def kill(self, pid):
        assert pid == self.process.pid
        self.signals.append(('kill', pid))
        self.process.kill()


class Tests(unittest.TestCase):
    def run_case(self, mode='success', *, sample=None, high=False, change_identity=False,
                 timeout=.7, handshake=.5, log_limit=256*1024):
        temporary = tempfile.TemporaryDirectory(prefix='llama-watchdog-synthetic-')
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        worker = root/'synthetic_worker.py'
        worker.write_text(WORKER, encoding='utf-8')
        backend = OwnedBackend(root, high=high, change_identity=change_identity)
        original = subprocess.Popen

        def own_popen(*args, **kwargs):
            process = original(*args, **kwargs)
            backend.process = process
            return process

        if sample is None:
            sample = lambda: {'available_bytes': 10*m.GiB,
                              'cgroup_headroom_bytes': 10*m.GiB}
        env = {k: v for k, v in os.environ.items() if k in ('SYSTEMROOT', 'WINDIR', 'PATH', 'TEMP', 'TMP')}
        with patch.object(m.subprocess, 'Popen', side_effect=own_popen):
            result = m.run_owned([TEST_PYTHON, '-B', str(worker), mode], root, env,
                                 timeout_seconds=timeout, handshake_seconds=handshake,
                                 interval_seconds=.02, terminate_grace_seconds=.1,
                                 log_limit_bytes=log_limit, _backend=backend, _sample=sample)
        # Identity-reuse simulations intentionally deny any watchdog signal.
        # The test harness may clean up its exact Popen handle afterwards.
        if backend.process is not None and backend.process.poll() is None:
            backend.process.terminate()
            backend.process.wait(timeout=3)
        return root, result, backend

    def test_gate_and_success(self):
        root, result, backend = self.run_case()
        self.assertEqual(result['status'], 'completed')
        self.assertTrue(result['gate_opened'])
        self.assertTrue((root/'loaded.marker').exists())
        self.assertEqual(result['RSS_cap_bytes'], 8*m.GiB)
        self.assertEqual(backend.signals, [])

    def test_gate_publication_only_after_complete_JSON(self):
        original_link = os.link
        observations = []
        def link_complete(source, destination):
            source, destination = Path(source), Path(destination)
            if destination.name == 'start.gate':
                self.assertEqual(source.name, '.start.gate.pending')
                self.assertFalse(destination.exists())
                value = json.loads(source.read_text('utf-8'))
                self.assertEqual(set(value), {'pid', 'create_time', 'RSS_cap_bytes', 'OS_floor_bytes'})
                self.assertGreater(value['RSS_cap_bytes'], 0)
                observations.append(value)
            return original_link(source, destination)
        with patch.object(m.os, 'link', side_effect=link_complete):
            root, result, _ = self.run_case()
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(len(observations), 1)
        self.assertEqual(json.loads((root/'start.gate').read_text()), observations[0])
        self.assertFalse((root/'.start.gate.pending').exists())

    def test_insufficient_budget_never_opens_gate(self):
        root, result, backend = self.run_case(sample=lambda: {'available_bytes': 2*m.GiB+1,
                                                             'cgroup_headroom_bytes': None})
        self.assertEqual(result['reason'], 'fresh_budget_insufficient')
        self.assertFalse((root/'start.gate').exists())
        self.assertFalse((root/'loaded.marker').exists())
        self.assertIsNotNone(backend.process.returncode)

    def test_handshake_deadline(self):
        root, result, backend = self.run_case('nohandshake', handshake=.15)
        self.assertEqual(result['reason'], 'handshake_deadline_exceeded')
        self.assertFalse(result['gate_opened'])
        self.assertIsNotNone(backend.process.returncode)

    def test_total_deadline(self):
        _, result, backend = self.run_case('timeout', timeout=.3, handshake=.25)
        self.assertEqual(result['reason'], 'deadline_exceeded')
        self.assertTrue(result['gate_opened'])
        self.assertIsNotNone(backend.process.returncode)

    def test_rss_signal_stops_owner(self):
        _, result, backend = self.run_case('timeout', high=True)
        self.assertEqual(result['reason'], 'RSS_cap')
        self.assertIsNotNone(backend.process.returncode)

    def test_memory_pressure_stops_owner(self):
        calls = [0]
        def sample():
            calls[0] += 1
            return {'available_bytes': 10*m.GiB if calls[0] < 4 else m.GiB,
                    'cgroup_headroom_bytes': None}
        _, result, backend = self.run_case('timeout', sample=sample)
        self.assertEqual(result['reason'], 'OS_memory_floor')
        self.assertIsNotNone(backend.process.returncode)

    def test_monitor_exception_failstop(self):
        calls = [0]
        def sample():
            calls[0] += 1
            if calls[0] > 2:
                raise OSError('synthetic-private-error-must-not-be-exported')
            return {'available_bytes': 10*m.GiB, 'cgroup_headroom_bytes': None}
        root, result, backend = self.run_case('timeout', sample=sample)
        self.assertEqual(result['reason'], 'monitor_error')
        self.assertNotIn('synthetic-private-error', (root/'watchdog-summary.json').read_text())
        self.assertIsNotNone(backend.process.returncode)

    def test_cgroup_headroom_stops_owner(self):
        calls = [0]
        def sample():
            calls[0] += 1
            return {'available_bytes': 10*m.GiB,
                    'cgroup_headroom_bytes': 10*m.GiB if calls[0] < 4 else m.GiB}
        _, result, backend = self.run_case('timeout', sample=sample)
        self.assertEqual(result['reason'], 'cgroup_memory_floor')
        self.assertIsNotNone(backend.process.returncode)

    def test_bad_handshake_identity(self):
        root, result, _ = self.run_case('badpid')
        self.assertEqual(result['reason'], 'handshake_invalid')
        self.assertFalse((root/'start.gate').exists())

    def test_identity_change_never_signals_reused_pid(self):
        _, result, backend = self.run_case('timeout', change_identity=True)
        self.assertEqual(result['primary_reason'], 'worker_identity_changed')
        self.assertEqual(result['status'], 'stopped')
        self.assertEqual(backend.signals, [])

    def test_output_cap(self):
        root, result, backend = self.run_case('overflow', log_limit=1000)
        self.assertEqual(result['reason'], 'log_size_cap')
        self.assertLessEqual((root/'worker.stdout.log').stat().st_size, 1000)
        self.assertIsNotNone(backend.process.returncode)

    def test_no_retry_same_run(self):
        root, _, backend = self.run_case()
        with self.assertRaisesRegex(ValueError, 'run_artifact_exists'):
            m.run_owned([sys.executable], root, {}, _backend=backend,
                        _sample=lambda: {'available_bytes': 10*m.GiB})

    def test_cleanup_never_signals_unrelated_or_reused_identity(self):
        class B:
            identities = {10: 1., 11: 2., 99: 3., 12: 999.}
            signals = []
            def identity(self, pid): return self.identities.get(pid)
            def children(self, pid): return [11] if pid == 10 else []
            def rss(self, pid): return 1
            def terminate(self, pid): self.signals.append(pid);self.identities.pop(pid, None)
            kill = terminate
        b = B()
        m._stop_owned(b, 10, 1., {10: 1., 11: 2., 12: 4.}, 0)
        self.assertEqual(set(b.signals), {10, 11})
        self.assertIn(99, b.identities)
        self.assertIn(12, b.identities)

    def test_colab_namespace_exact_bind_not_unlimited_root(self):
        mounts = ('1 0 0:27 / /sys/fs/cgroup ro - cgroup2 cgroup ro\n'
                  '2 0 0:27 /../../jupyter-children /var/colab/cgroup/jupyter-children ro - cgroup2 cgroup ro\n')
        binding = m.resolve_memory_cgroup('0::/../../jupyter-children\n', mounts)
        self.assertEqual(binding['base'].as_posix(), '/var/colab/cgroup/jupyter-children')
        self.assertTrue(binding['exact_namespace_root'])

    def test_colab_namespace_subgroup_stays_under_exact_mount(self):
        mounts = '2 0 0:27 /../../jupyter-children /var/colab/cgroup/jupyter-children ro - cgroup2 cgroup ro\n'
        binding = m.resolve_memory_cgroup('0::/../../jupyter-children/worker\n', mounts)
        self.assertEqual(binding['base'].as_posix(), '/var/colab/cgroup/jupyter-children/worker')

    def test_namespace_traversal_cannot_fall_back_to_root_or_escape(self):
        broad = '1 0 0:27 / /sys/fs/cgroup ro - cgroup2 cgroup ro\n'
        specific = '2 0 0:27 /../../jupyter-children /var/colab/cgroup/jupyter-children ro - cgroup2 cgroup ro\n'
        for membership, mounts in [('0::/../../jupyter-children\n', broad),
                                   ('0::/../../jupyter-children/../outside\n', broad+specific),
                                   ('0::/other\n', specific)]:
            with self.subTest(membership=membership), self.assertRaises(m.GuardStop):
                m.resolve_memory_cgroup(membership, mounts)

    def test_specific_normal_mount_and_v1_memory_controller(self):
        mounts = ('1 0 0:27 / /sys/fs/cgroup ro - cgroup2 cgroup ro\n'
                  '2 0 0:27 /tenant /limited ro - cgroup2 cgroup ro\n')
        self.assertEqual(m.resolve_memory_cgroup('0::/tenant/worker\n', mounts)['base'].as_posix(), '/limited/worker')
        v1 = m.resolve_memory_cgroup('4:memory:/tenant/worker\n',
                '3 0 0:28 /tenant /sys/fs/cgroup/memory rw - cgroup cgroup rw,memory\n')
        self.assertEqual(v1['version'], 1)
        self.assertEqual(v1['base'].as_posix(), '/sys/fs/cgroup/memory/worker')

    def test_invalid_mountpoint_and_ambiguous_binding_rejected(self):
        for mounts in ['1 0 0:27 /tenant /safe/../outside ro - cgroup2 cgroup ro\n',
                       '1 0 0:27 /tenant /a ro - cgroup2 cgroup ro\n2 0 0:28 /tenant /b ro - cgroup2 cgroup ro\n']:
            with self.subTest(mounts=mounts), self.assertRaises(m.GuardStop):
                m.resolve_memory_cgroup('0::/tenant\n', mounts)

    def test_wrong_filesystem_cannot_supply_cgroup_binding(self):
        with self.assertRaises(m.GuardStop):
            m.resolve_memory_cgroup('0::/tenant\n', '1 0 0:27 /tenant /tmp/fake ro - tmpfs tmpfs ro\n')


class ExitRaceTests(unittest.TestCase):
    """Deterministic Popen/identity interleavings; no OS process is launched."""
    def run_fake(self, mode, *, descendant=False, pressure=None, deadline=False,
                 log_error=False):
        temporary = tempfile.TemporaryDirectory(prefix='colab-guard-exit-synthetic-')
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        clock = [0.]

        class ImmediateThread:
            def __init__(self, target, args, **kwargs):self.target, self.args = target, args
            def start(self):self.target(*self.args)
            def join(self, timeout=None):pass
            def is_alive(self):return False

        class BrokenOutput:
            def read1(self, amount):raise OSError('synthetic-log-reader-failure')
            def close(self):pass

        class Process:
            pid = 100
            returncode = None
            pending_identity_exit = False
            def __init__(self):
                self.stdout = BrokenOutput() if log_error else io.BytesIO()
                self.stderr = io.BytesIO()
            def publish_handshake(self):
                (root/'handshake.json').write_text(json.dumps(dict(
                    pid=self.pid, create_time=1., baseline_rss_bytes=128*1024**2,
                    incremental_budget_bytes=m.GiB)), encoding='utf-8')
            def poll(self):
                if self.returncode is not None:return self.returncode
                if mode == 'pre_gate_zero':self.returncode=0;return 0
                if (root/'start.gate').exists():
                    if mode == 'stale_alive':self.returncode=0;return 0
                    self.pending_identity_exit=True
                return None
            def wait(self, timeout=None):
                if self.returncode is None:self.returncode=0
                return self.returncode

        process = Process()
        class Backend:
            survivor = descendant
            signals = []
            def identity(self, pid):
                if pid == 200:return 2. if self.survivor else None
                if process.returncode is not None:return None
                if process.pending_identity_exit:
                    if mode == 'live_reuse':return 999.
                    if mode == 'unknown_live':return None
                    process.returncode=9 if mode == 'race_nonzero' else 0
                    return None
                return 1.
            def children(self, pid):return [200] if self.survivor else []
            def rss(self, pid):return 128*1024**2
            def terminate(self, pid):
                self.signals.append(pid)
                if pid == 200:self.survivor=False
                else:process.returncode=-15
            kill = terminate
        backend = Backend()
        def sample():
            gated=(root/'start.gate').exists()
            return {'available_bytes':m.GiB if gated and pressure=='OS' else 10*m.GiB,
                    'cgroup_headroom_bytes':m.GiB if gated and pressure=='cgroup' else 10*m.GiB}
        def advance(seconds):clock[0]+=seconds
        def launch(*args,**kwargs):
            process.publish_handshake()
            return process
        with patch.object(m.subprocess,'Popen',side_effect=launch), \
             patch.object(m.threading,'Thread',ImmediateThread), \
             patch.object(m.time,'monotonic',side_effect=lambda:clock[0]), \
             patch.object(m.time,'sleep',side_effect=advance):
            summary=m.run_owned(['synthetic-no-launch'],root,{},
                timeout_seconds=.01 if deadline else 600,
                handshake_seconds=.01 if deadline else 120,
                interval_seconds=.02,terminate_grace_seconds=0,
                _backend=backend,_sample=sample)
        self.assertEqual(json.loads((root/'watchdog-summary.json').read_text()),summary)
        return summary,backend

    def test_identity_none_between_poll_and_identity_repolls_exit(self):
        result,backend=self.run_fake('race_zero')
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['worker_returncode'],0)
        self.assertEqual(result['final_worker_returncode'],0)
        self.assertEqual(result['primary_reason'],'worker_exited')
        self.assertEqual(backend.signals,[])

    def test_pre_poll_alive_root_is_not_a_surviving_descendant(self):
        result,_=self.run_fake('stale_alive')
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['worker_returncode'],0)

    def test_repolled_nonzero_exit_never_passes(self):
        result,_=self.run_fake('race_nonzero')
        self.assertEqual(result['status'],'stopped')
        self.assertEqual(result['worker_returncode'],9)
        self.assertEqual(result['final_worker_returncode'],9)

    def test_zero_exit_before_permission_never_passes(self):
        result,_=self.run_fake('pre_gate_zero')
        self.assertFalse(result['gate_opened'])
        self.assertEqual(result['status'],'stopped')
        self.assertEqual(result['reason'],'worker_exited_before_gate')
        self.assertEqual(result['final_worker_returncode'],0)

    def test_live_reused_identity_is_still_stopped_and_never_signalled(self):
        result,backend=self.run_fake('live_reuse')
        self.assertEqual(result['status'],'stopped')
        self.assertEqual(result['primary_reason'],'worker_identity_changed')
        self.assertEqual(result['final_worker_returncode'],0)
        self.assertEqual(backend.signals,[])

    def test_identity_unknown_but_still_running_is_not_success(self):
        result,backend=self.run_fake('unknown_live')
        self.assertEqual(result['status'],'stopped')
        self.assertEqual(result['primary_reason'],'worker_identity_changed')
        self.assertEqual(backend.signals,[])

    def test_known_live_descendant_prevents_completed_exit(self):
        result,backend=self.run_fake('race_zero',descendant=True)
        self.assertEqual(result['status'],'stopped')
        self.assertEqual(result['primary_reason'],'owned_descendant_survived')
        self.assertEqual(result['final_worker_returncode'],0)
        self.assertEqual(backend.signals,[200])

    def test_memory_floor_keeps_priority_over_exit_classification(self):
        for pressure,reason in [('OS','OS_memory_floor'),('cgroup','cgroup_memory_floor')]:
            with self.subTest(pressure=pressure):
                result,_=self.run_fake('race_zero',pressure=pressure)
                self.assertEqual(result['status'],'stopped')
                self.assertEqual(result['primary_reason'],reason)
                self.assertIn('final_worker_returncode',result)

    def test_deadline_keeps_priority_over_exit_classification(self):
        result,_=self.run_fake('race_zero',deadline=True)
        self.assertEqual(result['status'],'stopped')
        self.assertEqual(result['primary_reason'],'deadline_exceeded')
        self.assertIn('final_worker_returncode',result)

    def test_log_reader_error_keeps_priority_over_exit_classification(self):
        result,_=self.run_fake('race_zero',log_error=True)
        self.assertEqual(result['status'],'stopped')
        self.assertEqual(result['primary_reason'],'log_monitor_error')
        self.assertIn('final_worker_returncode',result)


if __name__ == '__main__':
    unittest.main()
