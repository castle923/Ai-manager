"""Display-only workshop references. Never registers, downloads or runs a model."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import threading
import uuid

from . import adapters
from .candidate_recommendations import RECIPES, PURPOSES, annotate_and_rank, _profiles as candidate_profiles
from .config import private_home
from .dashboard import Dashboard
from .inference import FileOwner

TASKS = {p['id']: p['label'] for p in PURPOSES}
POLICY = 1
KINDS = {'profile', 'candidate', 'registered'}
USER_TYPES = {'음성 합성':'tts', '음성 인식':'stt', '이미지 생성':'image', '언어 모델':'llm', '영상 추적':'tracking'}
FLOW = {
    'tts': ('새 한국어 문장', '지정 음성 합성 프로필로 처리', '새 WAV 음성'),
    'stt': ('새 WAV 음성', '음성 인식·전사', '새 전사 텍스트'),
    'llm': ('새 텍스트', '지정 언어 모델로 응답 생성', '새 응답 텍스트'),
    'image': ('새 문장', '지정 이미지 생성 파이프라인', '새 이미지'),
    'tracking': ('새 영상과 지정 지점', '프레임 사이의 지점 위치 추적', '새 궤적과 미리보기 · 영상 생성 아님'),
}


def packed(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(packed(value).encode()).hexdigest()


class ReferenceError(ValueError):
    pass


def task_checked(task):
    if not isinstance(task, str) or task not in TASKS:
        raise ReferenceError('reference_task_invalid')
    return task


def local_resources(home):
    """A timestamped observation, never an execution permission or VRAM guess."""
    result = dict(observed_at=datetime.now(timezone.utc).isoformat(), unit='bytes',
                  ram_total_bytes=None, ram_available_bytes=None, disk_free_bytes=None,
                  gpu_total_bytes=None, gpu_free_bytes=None, gpu_status='unmeasured',
                  source='Windows GlobalMemoryStatusEx and workspace disk_usage',
                  workspace_volume=Path(home).anchor, execution_permission=False)
    try:
        result['disk_free_bytes'] = shutil.disk_usage(home).free
    except OSError:
        pass
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        class Memory(ctypes.Structure):
            _fields_ = [('length', wintypes.DWORD), ('load', wintypes.DWORD)] + [
                (name, ctypes.c_ulonglong) for name in ('total_physical', 'available_physical',
                 'total_pagefile', 'available_pagefile', 'total_virtual', 'available_virtual', 'available_extended')]
        value = Memory()
        value.length = ctypes.sizeof(value)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(value)):
            result.update(ram_total_bytes=value.total_physical, ram_available_bytes=value.available_physical)
    return result


class WorkshopModels:
    def __init__(self, home, settings, resource_observer=local_resources):
        self.home = private_home(Path(home))
        self.settings = settings
        self.resource_observer = resource_observer
        self.path = self.home / 'workshop-representatives.json'
        self.lock = threading.RLock()

    def _catalog(self):
        return [(Path(__file__).with_name(filename).read_bytes(), purpose) for filename, purpose in RECIPES]

    def _profiles(self, task, catalog):
        values = []
        for raw, purpose in catalog:
            if purpose != task:
                continue
            manifest = json.loads(raw)
            identifier = manifest['model_id']
            from .task_runtime import environment
            runtime_state = environment(self.home, identifier) if identifier in adapters.CATALOG else None
            if runtime_state is None:
                from .preparation import Preparation
                runtime_state = Preparation(self.home, model_id=identifier).environment()
            requirements = None
            if identifier == 'qwen-image-2.1':
                from .image_worker import MEMORY_REQUIREMENTS
                requirements = dict(MEMORY_REQUIREMENTS)
            item = dict(kind='profile', id=identifier, name=manifest['name'], task=task,
                        source='bundled_fixed_manifest', revision=manifest['revision'],
                        manifest_sha256=hashlib.sha256(raw).hexdigest(), ownership='unconfirmed',
                        runtime=runtime_state['status'], requirements=requirements,
                        readiness_source='saved_runtime_record; current preflight not performed',
                        label='기준 모델 · 참고용 · 보유 미확인',
                        reason='앱의 고정 지원 프로필입니다. 성능 1위나 현재 소유·실행 성공을 뜻하지 않습니다.')
            item['fingerprint'] = digest(dict(policy=POLICY, facts={k: item[k] for k in ('kind', 'id', 'task', 'revision', 'manifest_sha256')}))
            values.append(item)
        return values

    def _candidates(self, task, profiles, catalog, include_unrelated=False):
        dashboard = Dashboard(self.home, read_only=True)
        snapshot = dashboard.snapshot(include_scan_settings=True)
        allowed = {(r['account'], r['alias'], r['id']) for r in self.settings.get('allowlist', [])}
        scan_roots = {}
        if snapshot['scans']:
            for scan in snapshot['scans']:
                roots = snapshot['_scan_settings'][scan['scan_id']].get('allowlist', [])
                relevant = [r for r in roots if r['account'] == scan['account']]
                if len({r['alias'] for r in relevant}) != len(relevant):
                    continue
                scan_roots[scan['scan_id']] = {r['alias']: r['id'] for r in relevant}
        rows = [r for r in snapshot['models'] if r['files'] and all(
            (r['account'], f['root'], scan_roots.get(r['scan_id'], {}).get(f['root'])) in allowed for f in r['files'])]
        _, ordered, _ = annotate_and_rank(rows, task, 'models', profiles=candidate_profiles([(json.loads(raw), purpose) for raw, purpose in catalog]))
        result = []
        manifests = {p['id']: p['manifest_sha256'] for p in profiles}
        for row in ordered:
            recommendation = row['recommendation']
            if not recommendation['related'] and not include_unrelated:
                continue
            hints = [p['id'] for p in recommendation['profile_name_candidates'] if p['purpose'] == task]
            item = dict(kind='candidate', id=row['id'], name=row['name'], task=task,
                        path=row['path'], family=row['family'],
                        account=row['account'], source='current_drive_inventory_metadata',
                        scan_id=row['scan_id'], scan_status=row['scan_status'],
                        profile_hints=hints, label='참고용 · Drive 메타데이터 후보',
                        ownership='metadata_observed_identity_unverified',
                        matched_profile_metadata=bool(recommendation['eligible']),
                        reasons=recommendation['reasons'], limitations=recommendation['limitations'],
                        file_count=row['count'], size_bytes=row['size'])
            item['fingerprint'] = digest(dict(policy=POLICY, task=task, scan=row['scan_id'],
                identity=row['id'], facts=[{k: f[k] for k in ('id', 'root', 'kind', 'size', 'modified', 'name')} for f in row['files']],
                scope=sorted(allowed), manifests=manifests, reasons=recommendation['reason_codes']))
            if include_unrelated:
                item['local_related'] = bool(recommendation['related'])
            result.append(item)
        return result

    def _registered(self, task, profiles, catalog):
        path = private_home(self.home / 'registry.sqlite3')
        if not path.exists():
            return [], 0
        mapped = {json.loads(raw)['model_id']: purpose for raw, purpose in catalog}
        result = []
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
            db.execute('PRAGMA query_only=ON')
            rows = db.execute('SELECT id,row_version,metadata_json,artifact_json,generation,fingerprint FROM models WHERE archived=0 ORDER BY id').fetchall()
        for identifier, version, metadata_raw, artifact_raw, generation, fingerprint in rows:
            metadata, artifact = json.loads(metadata_raw), json.loads(artifact_raw)
            adapter = artifact.get('adapter_id')
            # The public registry's legacy missing-adapter TTS fallback is NOT a task classification.
            classified = mapped.get(adapter) or (USER_TYPES.get(metadata.get('type')) if not adapter else None)
            if classified != task:
                continue
            item = dict(kind='registered', id=identifier, name=metadata['name'], task=task,
                        source='workspace_registry', adapter_id=adapter, row_version=version,
                        label='등록 모델 · 실행 준비 별도 확인' if adapter else '참고용 · 사용자 용도만 지정 · 실행 미지원', ownership='user_registered',
                        task_evidence='explicit_adapter' if adapter else 'user_metadata_type_only',
                        reason='명시된 실행 프로필의 등록입니다. 실제 파일·환경·자원 검증은 실행 화면에서 확인하세요.' if adapter else '사용자가 관리 용도를 지정했습니다. 지원 실행 프로필은 지정되지 않았으며 이 분류로 실행할 수 없습니다.')
            item['fingerprint'] = digest(dict(policy=POLICY, task=task, id=identifier,
                row_version=version, generation=generation, artifact_fingerprint=fingerprint,
                artifact=artifact, metadata=metadata, catalog=digest([(hashlib.sha256(raw).hexdigest(), purpose) for raw, purpose in catalog])))
            result.append(item)
        return result, len(rows)

    def _sidecar_snapshot(self):
        path = private_home(self.path)
        if not path.exists():
            return None
        def identity(stat):
            return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
        before = path.stat()
        if before.st_size > 16384:
            raise ReferenceError('representative_invalid')
        raw = path.read_bytes()
        if identity(before) != identity(private_home(self.path).stat()):
            raise ReferenceError('representative_stale_preserved')
        return identity(before), raw

    def _choices_from_snapshot(self, snapshot):
        try:
            if snapshot is None:
                return dict(schema_version=1, revision=0, choices={})
            value = json.loads(snapshot[1].decode('utf8'))
            if not isinstance(value, dict) or set(value) != {'schema_version', 'revision', 'choices'} or type(value['schema_version']) is not int or value['schema_version'] != 1 or type(value['revision']) is not int or not 1 <= value['revision'] < 2**53 or not isinstance(value['choices'], dict):
                raise ReferenceError('representative_invalid')
            for task, choice in value['choices'].items():
                task_checked(task)
                self._validate_choice(choice)
            return value
        except (OSError, ValueError, TypeError) as error:
            if isinstance(error, ReferenceError):
                raise
            raise ReferenceError('representative_unavailable') from None

    def read_choices(self):
        try:
            return self._choices_from_snapshot(self._sidecar_snapshot())
        except OSError:
            raise ReferenceError('representative_unavailable') from None

    @staticmethod
    def _validate_choice(choice):
        if not isinstance(choice, dict) or set(choice) != {'kind', 'id', 'fingerprint'} or not isinstance(choice['kind'], str) or choice['kind'] not in KINDS or not isinstance(choice['id'], str) or not 1 <= len(choice['id']) <= 100 or not isinstance(choice['fingerprint'], str) or not re.fullmatch('[a-f0-9]{64}', choice['fingerprint']):
            raise ReferenceError('representative_invalid')

    def overview(self, task):
        task_checked(task)
        catalog = self._catalog()
        profiles = self._profiles(task, catalog)
        candidates = self._candidates(task, profiles, catalog)
        registered, total_registered = self._registered(task, profiles, catalog)
        state = self.read_choices()
        choice = state['choices'].get(task)
        items = profiles + registered + candidates
        chosen = next((i for i in items if choice and all(i[k] == choice[k] for k in ('kind', 'id', 'fingerprint'))), None)
        resources = self.resource_observer(self.home)
        for profile in profiles:
            requirements = profile['requirements']
            checks = []
            if requirements:
                for minimum, observed in (('ram_available_min_bytes', 'ram_available_bytes'), ('disk_free_min_bytes', 'disk_free_bytes'), ('gpu_total_min_bytes', 'gpu_total_bytes'), ('gpu_free_min_bytes', 'gpu_free_bytes')):
                    value = resources.get(observed)
                    checks.append(dict(metric=observed, required_bytes=requirements[minimum], observed_bytes=value,
                                       status='unknown' if value is None else 'below_recipe_minimum' if value < requirements[minimum] else 'observed_minimum_met'))
            profile['resource_checks'] = checks
        return dict(policy_version=POLICY, task=task, task_label=TASKS[task], mode='reference',
                    execution_allowed=False, sampled_generation=False, profiles=profiles,
                    candidates=candidates, registered=registered, registered_total=total_registered,
                    representative=dict(revision=state['revision'], status='current' if chosen else 'expired' if choice else 'not_selected',
                                        choice=choice, item=chosen, fallback=profiles[0] if not choice and profiles else None),
                    resources=resources, workflow=FLOW[task],
                    explanation='Drive 수집은 모델 등록이 아닙니다. 실행 선택 목록은 등록한 지원 프로필 모델만 사용합니다. 등록 0개는 RAM 부족 판정이 아닙니다.')

    def preview(self, task, choice):
        self._validate_choice(choice)
        view = self.overview(task)
        item = next((i for i in view['profiles'] + view['registered'] + view['candidates'] if all(i[k] == choice[k] for k in ('kind', 'id', 'fingerprint'))), None)
        if item is None:
            raise ReferenceError('reference_expired')
        return dict(mode='reference', execution_allowed=False, sampled_generation=False,
                    item=item, workflow=view['workflow'], resources=view['resources'],
                    missing_checks=['모델·revision 실제 식별', '전체 필수 가중치와 SHA-256', '현재 실행 환경·자원 사전 검사', '새 실제 출력과 품질'])

    def choose(self, data):
        if not isinstance(data, dict) or set(data) != {'task', 'revision', 'choice'} or type(data['revision']) is not int or not 0 <= data['revision'] < 2**53 - 1:
            raise ReferenceError('representative_invalid')
        task_checked(data['task'])
        if data['choice'] is not None:
            self._validate_choice(data['choice'])
        with self.lock:
            owner = None
            temporary = None
            try:
                owner = FileOwner(private_home(self.home / 'workshop-representatives-owner.lock'))
                if not owner.handle:
                    raise ReferenceError('representative_busy')
                expected_sidecar = self._sidecar_snapshot()
                old = self._choices_from_snapshot(expected_sidecar)
                if old['revision'] != data['revision']:
                    raise ReferenceError('representative_stale')
                # Reuse this coherent precommit view for the acknowledgement.
                # A later resource/DB read must not turn a committed save into an error.
                view = self.overview(data['task'])
                chosen = None
                if data['choice'] is not None:
                    chosen = next((i for i in view['profiles'] + view['registered'] + view['candidates']
                                   if all(i[k] == data['choice'][k] for k in ('kind','id','fingerprint'))), None)
                    if chosen is None:
                        raise ReferenceError('reference_expired')
                choices = dict(old['choices'])
                if data['choice'] is None:
                    choices.pop(data['task'], None)
                else:
                    choices[data['task']] = dict(data['choice'])
                value = dict(schema_version=1, revision=old['revision'] + 1, choices=choices)
                temporary = private_home(self.home / ('workshop-representatives-' + uuid.uuid4().hex + '.tmp'))
                with temporary.open('x', encoding='utf8') as stream:
                    json.dump(value, stream, ensure_ascii=False, indent=2)
                    stream.flush()
                    os.fsync(stream.fileno())
                if self._sidecar_snapshot() != expected_sidecar:
                    raise ReferenceError('representative_stale_preserved')
                os.replace(temporary, self.path)
                view['representative'] = dict(revision=value['revision'], status='current' if chosen else 'not_selected',
                    choice=data['choice'], item=chosen, fallback=None if chosen else view['profiles'][0] if view['profiles'] else None,
                    saved=True, source_validation='precommit_snapshot; later observation changes require refresh')
                return view
            except OSError:
                raise ReferenceError('representative_unavailable') from None
            finally:
                if temporary is not None and temporary.is_file():
                    temporary.unlink()
                if owner is not None:
                    owner.close()
