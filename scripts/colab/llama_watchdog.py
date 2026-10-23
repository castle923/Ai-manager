"""Owned-worker memory guard. No model/auth/network code; never prints env/argv.

The worker must not log secrets. After imports and meta-only placement it writes
handshake.json exclusively, then waits for start.gate before loading weights.
This sampled watchdog is not an OS memory limit or a guarantee against OOM.
"""
import json
import math
import os
from pathlib import Path
import re
import subprocess
import threading
import time

GiB = 1024 ** 3


class GuardStop(Exception):
    pass


class PsutilBackend:
    def __init__(self):
        import psutil
        self.psutil = psutil

    def identity(self, pid):
        try:
            process = self.psutil.Process(pid)
            if not process.is_running() or process.status() == self.psutil.STATUS_ZOMBIE:
                return None
            return process.create_time()
        except self.psutil.NoSuchProcess:
            return None

    def children(self, pid):
        try:
            return [p.pid for p in self.psutil.Process(pid).children(recursive=True)]
        except self.psutil.NoSuchProcess:
            return []

    def rss(self, pid):
        try:
            return self.psutil.Process(pid).memory_info().rss
        except self.psutil.NoSuchProcess:
            return 0

    def terminate(self, pid):
        self.psutil.Process(pid).terminate()

    def kill(self, pid):
        self.psutil.Process(pid).kill()


def _posix_normalized(path):
    """Lexically normalize an absolute proc/mount POSIX path, clamped at root.

    This is only a comparison key. A proc path is never joined to a filesystem
    path before validated mount-root mapping has removed the namespace prefix.
    """
    if not isinstance(path, str) or not path.startswith('/') or '\x00' in path:
        raise GuardStop('cgroup_path_invalid')
    parts = []
    for part in path.split('/'):
        if part in ('', '.'):
            continue
        if part == '..':
            if parts:
                parts.pop()
        else:
            parts.append(part)
    return '/'+('/'.join(parts))


def _mount_unescape(value):
    # mountinfo escapes whitespace and backslashes with octal, not URL escapes.
    return re.sub(r'\\([0-7]{3})', lambda match: chr(int(match.group(1), 8)), value)


def _under(path, root):
    return path == root or root == '/' or path.startswith(root+'/')


def resolve_memory_cgroup(proc_cgroup, mountinfo):
    """Map this namespace's memory cgroup to a verified cgroup mount.

    Escaping proc paths such as /../../jupyter-children require matching raw
    namespace-prefix evidence from mountinfo; the broad '/' mount is not an
    acceptable fallback. Prefer the most specific root and fail on ambiguity.
    The returned path contains no dot-dot components. This function performs no IO.
    """
    memberships = []
    for line in proc_cgroup.splitlines():
        fields = line.split(':', 2)
        if len(fields) != 3:
            raise GuardStop('cgroup_membership_invalid')
        _, controllers, raw_path = fields
        if controllers == '':
            memberships.append((2, raw_path))
        elif 'memory' in controllers.split(','):
            memberships.append((1, raw_path))
    if not memberships:
        return None
    # Unified hierarchy takes precedence when present.
    version, proc_raw = sorted(memberships, key=lambda value: value[0], reverse=True)[0]
    proc_normal = _posix_normalized(proc_raw)
    candidates = []
    for line in mountinfo.splitlines():
        left, separator, right = line.partition(' - ')
        if not separator:
            continue
        fields, tail = left.split(), right.split()
        if len(fields) < 6 or len(tail) < 3:
            continue
        fs_type = tail[0]
        if version == 2 and fs_type != 'cgroup2':
            continue
        if version == 1 and (fs_type != 'cgroup' or 'memory' not in tail[2].split(',')):
            continue
        if re.fullmatch(r'[0-9]+:[0-9]+', fields[2]) is None:
            continue
        raw_root = _mount_unescape(fields[3])
        mountpoint = _mount_unescape(fields[4])
        root_normal = _posix_normalized(raw_root)
        mount_normal = _posix_normalized(mountpoint)
        # A mountpoint is an actual access path, unlike the comparison-only root.
        if '..' in mountpoint.split('/') or mount_normal != mountpoint.rstrip('/'):
            continue
        if not _under(proc_normal, root_normal):
            continue
        if '..' in proc_raw.split('/') or '..' in raw_root.split('/'):
            # Normalization alone cannot establish namespace equivalence. Require
            # the same raw escaping prefix; e.g. a matching read-only bind root.
            if '..' not in raw_root.split('/') or not _under(proc_raw, raw_root):
                continue
        suffix = proc_normal[len(root_normal):].lstrip('/') if root_normal != '/' else proc_normal.lstrip('/')
        base = mount_normal+('/'+suffix if suffix else '')
        if '..' in base.split('/') or not _under(base, mount_normal):
            raise GuardStop('cgroup_mount_escape_rejected')
        candidates.append((len([part for part in root_normal.split('/') if part]),
                           base, fields[2], raw_root == proc_raw))
    if not candidates:
        raise GuardStop('cgroup_mount_unresolved')
    depth = max(value[0] for value in candidates)
    best = [value for value in candidates if value[0] == depth]
    if len({(value[1], value[2]) for value in best}) != 1:
        raise GuardStop('cgroup_mount_ambiguous')
    return {'version': version, 'base': Path(best[0][1]),
            'mount_device': tuple(int(value) for value in best[0][2].split(':')),
            'exact_namespace_root': best[0][3]}


def memory_sample():
    """Linux MemAvailable plus finite namespace cgroup limit, read-only."""
    values = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        parts = line.split()
        if parts[0] == 'MemAvailable:':
            values['available_bytes'] = int(parts[1]) * 1024
    if 'available_bytes' not in values:
        raise GuardStop('memory_measurement_failed')
    values.update(cgroup_current_bytes=None, cgroup_max_bytes=None,
                  cgroup_headroom_bytes=None, cgroup_file_bytes=None)
    binding = resolve_memory_cgroup(Path('/proc/self/cgroup').read_text(),
                                    Path('/proc/self/mountinfo').read_text())
    if binding is not None:
        base, version = binding['base'], binding['version']
        if not base.is_dir() or base.is_symlink() or base.resolve() != base:
            raise GuardStop('cgroup_access_path_invalid')
        device = base.stat().st_dev
        if (os.major(device), os.minor(device)) != binding['mount_device']:
            raise GuardStop('cgroup_mount_device_mismatch')
        current_name, max_name = (('memory.current', 'memory.max') if version == 2
                                  else ('memory.usage_in_bytes', 'memory.limit_in_bytes'))
        paths = [base/current_name, base/max_name, base/'memory.stat']
        if any(not path.is_file() or path.is_symlink() or path.resolve().parent != base
               or path.stat().st_dev != device for path in paths):
            raise GuardStop('cgroup_memory_file_invalid')
        current = int(paths[0].read_text().strip())
        maximum = paths[1].read_text().strip()
        maximum = None if maximum == 'max' else int(maximum)
        # v1 uses an enormous integer for an unlimited memory controller.
        if maximum is not None and maximum >= (1 << 60):
            maximum = None
        values.update(cgroup_current_bytes=current, cgroup_max_bytes=maximum,
                      cgroup_headroom_bytes=None if maximum is None else maximum-current)
        stat = {}
        for line in paths[2].read_text().splitlines():
            key, value = line.split()
            if key in ('file', 'cache'):
                stat[key] = int(value)
        values['cgroup_file_bytes'] = stat.get('file', stat.get('cache'))
    return values


def _same(backend, pid, identity):
    actual = backend.identity(pid)
    return actual is not None and actual == identity


def _record_confirmed_exit(child, backend, known, summary, returncode):
    """Classify only the exact Popen exit, retaining proven descendant checks."""
    if any(pid != child.pid and _same(backend, pid, identity)
           for pid, identity in known.items()):
        raise GuardStop('owned_descendant_survived')
    summary.update(status='completed' if returncode == 0 and summary['gate_opened'] else 'stopped',
                   reason='worker_exited' if summary['gate_opened'] else 'worker_exited_before_gate',
                   worker_returncode=returncode)


def _snapshot(backend, root_pid, root_identity, known):
    if _same(backend, root_pid, root_identity):
        # A PID is admitted only through the owned root's current process tree.
        for pid in backend.children(root_pid):
            identity = backend.identity(pid)
            if identity is not None:
                prior = known.get(pid)
                if prior is not None and prior != identity:
                    raise GuardStop('descendant_identity_changed')
                known[pid] = identity
    total = 0
    alive = []
    for pid, identity in list(known.items()):
        if _same(backend, pid, identity):
            total += backend.rss(pid)
            alive.append(pid)
    return total, alive


def _stop_owned(backend, root_pid, root_identity, known, grace):
    """Best effort termination only of root / previously proven descendants."""
    errors = False
    try:
        _snapshot(backend, root_pid, root_identity, known)
    except Exception:
        errors = True
    # Children first; no global process scans or name-based termination.
    order = [pid for pid in known if pid != root_pid] + [root_pid]
    for method in ('terminate', 'kill'):
        for pid in order:
            try:
                if _same(backend, pid, known[pid]):
                    getattr(backend, method)(pid)
            except Exception:
                errors = True
        if method == 'terminate':
            until = time.monotonic() + grace
            while time.monotonic() < until:
                try:
                    if not any(_same(backend, pid, known[pid]) for pid in order):
                        break
                except Exception:
                    errors = True
                    break
                time.sleep(min(.05, max(0, until-time.monotonic())))
    remaining = []
    for pid in order:
        try:
            if _same(backend, pid, known[pid]):
                remaining.append(pid)
        except Exception:
            errors = True
    return {'remaining_owned_count': len(remaining), 'cleanup_measurement_error': errors}


def _finite_integer(value):
    return type(value) is int and value >= 0


def run_owned(command, run_dir, env, *, timeout_seconds=600, handshake_seconds=120,
              interval_seconds=.2, os_floor_bytes=2*GiB, hard_rss_cap_bytes=8*GiB,
              log_limit_bytes=256*1024, terminate_grace_seconds=3,
              _backend=None, _sample=None):
    """Run once, returning only numeric/status evidence. No automatic retry.

    Test-only backend/sample injection does not occur in the production caller.
    Logs are bounded but not redacted: the token-free worker must emit no secrets.
    The supplied command must be an argv list; no shell is used.
    """
    if not isinstance(command, list) or not command or not all(isinstance(x, str) for x in command):
        raise ValueError('argv_list_required')
    if not (0 < timeout_seconds <= 600 and 0 < handshake_seconds <= timeout_seconds
            and 0 < interval_seconds <= .2 and 0 <= terminate_grace_seconds <= 3
            and os_floor_bytes >= 2*GiB and 0 < hard_rss_cap_bytes <= 8*GiB
            and 0 < log_limit_bytes <= 256*1024):
        raise ValueError('guard_policy_invalid')
    backend = _backend if _backend is not None else PsutilBackend()
    sample = _sample if _sample is not None else memory_sample
    root = Path(run_dir)
    if not root.is_absolute() or not root.is_dir() or root.is_symlink():
        raise ValueError('new_absolute_run_directory_required')
    names = ['handshake.json', 'start.gate', '.start.gate.pending', 'watchdog-summary.json',
             'worker.stdout.log', 'worker.stderr.log', 'watchdog-once.marker']
    if any((root / name).exists() or (root / name).is_symlink() for name in names):
        raise ValueError('run_artifact_exists_no_retry')
    with (root / 'watchdog-once.marker').open('x') as marker:
        marker.write('one_owned_attempt\n')
    handshake, gate = root/'handshake.json', root/'start.gate'
    argv = command + ['--watchdog-handshake', str(handshake), '--watchdog-gate', str(gate)]
    started = time.monotonic()
    child = None
    known = {}
    root_identity = None
    io_failed = threading.Event()
    io_overflow = threading.Event()
    counters = {'stdout': 0, 'stderr': 0}
    threads = []
    log_files = []
    summary = {'status': 'stopped', 'reason': 'monitor_error', 'gate_opened': False,
               'peak_owned_RSS_bytes': 0, 'minimum_available_RAM_bytes': None,
               'minimum_cgroup_headroom_bytes': None, 'samples': 0,
               'peak_cgroup_current_bytes': None, 'last_cgroup_max_bytes': None,
               'peak_cgroup_file_bytes': None,
               'automatic_retry': False, 'sampled_guard_not_OS_memory_limit': True}

    def drain(stream, target, label):
        try:
            while True:
                block = stream.read1(4096)
                if not block:
                    break
                allowance = log_limit_bytes - counters[label]
                if allowance > 0:
                    part = block[:allowance]
                    target.write(part)
                    counters[label] += len(part)
                    target.flush()
                if len(block) > allowance:
                    io_overflow.set()
        except Exception:
            io_failed.set()
        finally:
            stream.close()

    try:
        # Measurement failures before spawn must never start the model worker.
        initial = sample()
        if initial['available_bytes'] < os_floor_bytes:
            raise GuardStop('OS_memory_floor')
        child = subprocess.Popen(argv, shell=False, stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 cwd=str(root), env=env)
        root_identity = backend.identity(child.pid)
        if root_identity is None:
            raise GuardStop('worker_identity_unavailable')
        known[child.pid] = root_identity
        for label, stream in [('stdout', child.stdout), ('stderr', child.stderr)]:
            target = (root / ('worker.'+label+'.log')).open('xb')
            log_files.append(target)
            thread = threading.Thread(target=drain, args=(stream, target, label), daemon=True)
            thread.start()
            threads.append(thread)
        while True:
            elapsed = time.monotonic() - started
            if elapsed >= timeout_seconds:
                raise GuardStop('deadline_exceeded')
            if io_failed.is_set():
                raise GuardStop('log_monitor_error')
            if io_overflow.is_set():
                raise GuardStop('log_size_cap')
            rss, alive = _snapshot(backend, child.pid, root_identity, known)
            memory = sample()
            summary['samples'] += 1
            summary['peak_owned_RSS_bytes'] = max(summary['peak_owned_RSS_bytes'], rss)
            available = memory['available_bytes']
            prior = summary['minimum_available_RAM_bytes']
            summary['minimum_available_RAM_bytes'] = available if prior is None else min(prior, available)
            headroom = memory.get('cgroup_headroom_bytes')
            for source, destination in [('cgroup_current_bytes', 'peak_cgroup_current_bytes'),
                                        ('cgroup_file_bytes', 'peak_cgroup_file_bytes')]:
                value = memory.get(source)
                if value is not None:
                    prior = summary[destination]
                    summary[destination] = value if prior is None else max(prior, value)
            summary['last_cgroup_max_bytes'] = memory.get('cgroup_max_bytes')
            if headroom is not None:
                prior = summary['minimum_cgroup_headroom_bytes']
                summary['minimum_cgroup_headroom_bytes'] = headroom if prior is None else min(prior, headroom)
            if available < os_floor_bytes:
                raise GuardStop('OS_memory_floor')
            if headroom is not None and headroom < os_floor_bytes:
                raise GuardStop('cgroup_memory_floor')
            if rss >= summary.get('RSS_cap_bytes', hard_rss_cap_bytes):
                raise GuardStop('RSS_cap')
            returncode = child.poll()
            if returncode is not None:
                _record_confirmed_exit(child, backend, known, summary, returncode)
                break
            identity = backend.identity(child.pid)
            if identity != root_identity:
                # A process can exit after poll() but before the identity sample.
                # Accept only a newly confirmed Popen exit, never a changed live PID.
                returncode = child.poll() if identity is None else None
                if returncode is None:
                    raise GuardStop('worker_identity_changed')
                _record_confirmed_exit(child, backend, known, summary, returncode)
                break
            if not summary['gate_opened'] and handshake.exists():
                if handshake.is_symlink() or handshake.stat().st_size > 64*1024:
                    raise GuardStop('handshake_invalid')
                try:
                    data = json.loads(handshake.read_text(encoding='utf-8'))
                except json.JSONDecodeError:
                    # Worker may still be publishing its small exclusive JSON.
                    # No permission is granted until parsing and every guard pass.
                    if elapsed >= handshake_seconds:
                        raise GuardStop('handshake_invalid')
                    time.sleep(interval_seconds)
                    continue
                if (data.get('pid') != child.pid or type(data.get('create_time')) not in (int, float)
                        or not math.isfinite(data['create_time'])
                        or abs(data['create_time']-root_identity) > .001
                        or not _finite_integer(data.get('baseline_rss_bytes'))
                        or not _finite_integer(data.get('incremental_budget_bytes'))):
                    raise GuardStop('handshake_invalid')
                baseline = max(data['baseline_rss_bytes'], rss)
                incremental = data['incremental_budget_bytes']
                cap = min(hard_rss_cap_bytes, baseline+available-os_floor_bytes)
                if headroom is not None:
                    cap = min(cap, baseline+headroom-os_floor_bytes)
                if baseline+incremental >= cap or incremental+os_floor_bytes > available:
                    raise GuardStop('fresh_budget_insufficient')
                if headroom is not None and incremental+os_floor_bytes > headroom:
                    raise GuardStop('fresh_cgroup_budget_insufficient')
                # Recheck root identity and liveness immediately before publishing permission.
                if child.poll() is not None or not _same(backend, child.pid, root_identity):
                    raise GuardStop('worker_identity_changed')
                pending = root/'.start.gate.pending'
                with pending.open('x', encoding='utf-8') as output:
                    json.dump({'pid': child.pid, 'create_time': root_identity,
                               'RSS_cap_bytes': cap, 'OS_floor_bytes': os_floor_bytes}, output)
                    output.flush()
                    os.fsync(output.fileno())
                os.link(pending, gate)
                pending.unlink()
                summary.update(gate_opened=True, baseline_RSS_bytes=baseline,
                               incremental_budget_bytes=incremental, RSS_cap_bytes=cap,
                               handshake_available_RAM_bytes=available,
                               handshake_cgroup_headroom_bytes=headroom)
            if not summary['gate_opened'] and elapsed >= handshake_seconds:
                raise GuardStop('handshake_deadline_exceeded')
            time.sleep(interval_seconds)
    except GuardStop as error:
        summary.update(status='stopped', reason=error.args[0])
    except (Exception, KeyboardInterrupt):
        summary.update(status='stopped', reason='monitor_error')
    finally:
        summary['primary_reason'] = summary['reason']
        if child is not None:
            if root_identity is not None:
                summary.update(_stop_owned(backend, child.pid, root_identity, known, terminate_grace_seconds))
            else:
                # Popen is the exact just-created process handle, never a searched PID.
                child.terminate()
                try:
                    child.wait(timeout=terminate_grace_seconds)
                except subprocess.TimeoutExpired:
                    child.kill()
            try:
                summary['final_worker_returncode'] = child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                summary.update(status='stopped', reason='owned_cleanup_incomplete')
            for thread in threads:
                thread.join(timeout=1)
            if any(thread.is_alive() for thread in threads):
                summary.update(status='stopped', reason='log_reader_cleanup_incomplete')
        for target in log_files:
            target.close()
        summary.update(stdout_saved_bytes=counters['stdout'], stderr_saved_bytes=counters['stderr'],
                       elapsed_seconds=round(time.monotonic()-started, 3))
        if io_overflow.is_set():
            summary.update(status='stopped', reason='log_size_cap')
        if io_failed.is_set():
            summary.update(status='stopped', reason='log_monitor_error')
        with (root/'watchdog-summary.json').open('x', encoding='utf-8') as output:
            json.dump(summary, output, indent=2)
    return summary
