"""Build a disabled-by-default notebook from explicit, reviewed source inputs.

Only standard-library local reads/writes are used. No model, auth or network
access is performed by this builder. Existing output directories are rejected.
"""
import argparse
import ast
import base64
import hashlib
import json
from pathlib import Path
import shutil
import zlib

ORIGINAL_SHA = 'b9ed7fdfa41b39c0d2dbdb31fb677ae6f7c51d5a6ae447778fd3ece6ede42531'
GUARD_SHA = '218747316b9fdca77b17983feb531dccae979ded78ba39fe91428b804c6e358b'
OLD_GUARD_SHA = 'e708957971410a3594d9174e11b15cd401cbf9971f75924c9c94407478b19b14'
R02_INPUTS = {
    'cache_safe_verify.py': ('CACHE_SAFE_VERIFY.public.py', '5ff0a50263b3c6a75d7d6b632a50c0bd733d2a3c2cfb864a212ff04bce0fd75d'),
    'shard_cache_advisor.py': ('SHARD_CACHE_ADVISOR.public.py', 'c499fc96f0d7ed58cf561adcb449eb46efabdf2df3c3be047ca43aa1efb143e5'),
    'llama_worker.py': ('LLAMA_INT8_PERIODIC_CACHE_WORKER.public.py', 'a833fcbef1bd7efb415d324213703f83285694b5522c14c64c25657674f525d4'),
}
NAME = 'Llama_Free_T4_INT8_Exit_Confirmation.ipynb'
RESULT_HELPER_SHA = '7a43a8c2101c899236642e80a703e59ac2a17fd6e89c90c1476c49208d6b6311'
RESULT_HELPER_ORIGINAL_SHA = 'c8a3a712a3ed478441ecff1af63088593d669e8d6d0e4a6a5e5ca9db9e086fe8'
MINIMUM_FREE_BYTES = 500_000_000_000
FILESYSTEM_ALLOWANCE_BYTES = 1024 * 1024


def digest(data):
    return hashlib.sha256(data).hexdigest()


def pinned_read(path, expected):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('source_not_regular')
    data = path.read_bytes()
    if digest(data) != expected:
        raise ValueError('source_hash_mismatch')
    return data


def assignment(source, name):
    matches = [node for node in ast.parse(source).body if isinstance(node, ast.Assign)
               and any(isinstance(t, ast.Name) and t.id == name for t in node.targets)]
    if len(matches) != 1:
        raise ValueError('assignment_not_unique')
    return matches[0]


def replace_assignment(source, name, replacement):
    node = assignment(source, name)
    lines = source.splitlines(keepends=True)
    lines[node.lineno - 1:node.end_lineno] = [replacement + '\n']
    return ''.join(lines)


RESET_RUNTIME = '''# A failed new preparation must not reuse any prior run's readiness.
for stale_name in ('ROOT','PY','META','FRESH_META','FRESH_META_TIME','DOWNLOAD','MODEL','WORK','RUNTIME_CONTEXT','DOWNLOAD_CONTEXT','load_reviewed'):
    globals().pop(stale_name, None)
'''
CONTEXT_VALUE = "(globals().get('ROOT'), globals().get('PY'), globals().get('META'), globals().get('FRESH_META_TIME'), globals().get('env'), json.dumps(globals().get('FRESH_META'),sort_keys=True), tuple(sorted((name,item['sha256']) for name,item in globals().get('PAYLOADS',{}).items())))"
CHECK_RUNTIME = "assert globals().get('RUNTIME_CONTEXT') is not None and RUNTIME_CONTEXT==" + CONTEXT_VALUE + ", 'runtime_context_missing_or_changed'\n"

CONTROLS = '''# Local preparation is not permission for remote execution.
USER_CONFIRMED_FREE_ACCOUNT_NO_PAID_CU = False # @param {type:"boolean"}
USER_CONFIRMED_FREE_T4 = False # @param {type:"boolean"}
USER_APPROVED_RUNTIME_AND_LLAMA_EXPERIMENT = False # @param {type:"boolean"}
ALLOW_RUNTIME_DOWNLOAD = False # @param {type:"boolean"}
ALLOW_MODEL_DOWNLOAD = False # @param {type:"boolean"}
ALLOW_MODEL_EXECUTION = False # @param {type:"boolean"}
'''

DOWNLOAD = '''assert ALLOW_MODEL_DOWNLOAD, 'model_download_disabled'
assert USER_CONFIRMED_FREE_ACCOUNT_NO_PAID_CU and USER_CONFIRMED_FREE_T4 and USER_APPROVED_RUNTIME_AND_LLAMA_EXPERIMENT
globals().pop('DOWNLOAD',None);globals().pop('DOWNLOAD_CONTEXT',None)
''' + CHECK_RUNTIME + '''
assert FRESH_META['status']=='INT8_preflight_candidate'
assert time.monotonic()-FRESH_META_TIME<600, 'fresh_preflight_expired_before_token_prompt'
import importlib.util
def load_reviewed(name, filename):
    path=ROOT/filename
    assert hashlib.sha256(path.read_bytes()).hexdigest()==PAYLOADS[filename]['sha256']
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module
downloader=load_reviewed('fixed_download','llama_download.py')
manifest=json.loads((ROOT/'model-manifest.json').read_text())
assert downloader.fixed_manifest()['files']==manifest['files'] and downloader.fixed_manifest()['revision']==manifest['revision']
DOWNLOAD=downloader.download_fixed(ROOT)
print('__DOWNLOAD_STATUS__'+json.dumps({k:DOWNLOAD[k] for k in ('status','reason','application_body_bytes','token_saved','full_weight_SHA_verified')}))
assert DOWNLOAD['status']=='completed' and DOWNLOAD['file_count']==10 and DOWNLOAD['total_bytes']==16_069_722_669 and DOWNLOAD['full_weight_SHA_verified']
assert pathlib.Path(DOWNLOAD['model_path'])==ROOT/'model', 'download_context_path_mismatch'
DOWNLOAD_CONTEXT=(RUNTIME_CONTEXT,load_reviewed)
'''

EXECUTE = '''assert ALLOW_MODEL_EXECUTION, 'model_execution_disabled'
assert USER_CONFIRMED_FREE_ACCOUNT_NO_PAID_CU and USER_CONFIRMED_FREE_T4 and USER_APPROVED_RUNTIME_AND_LLAMA_EXPERIMENT
''' + CHECK_RUNTIME + '''assert globals().get('DOWNLOAD_CONTEXT')==(RUNTIME_CONTEXT,globals().get('load_reviewed')), 'download_context_missing_or_changed'
assert DOWNLOAD['status']=='completed' and DOWNLOAD['file_count']==10 and DOWNLOAD['total_bytes']==16_069_722_669 and DOWNLOAD['full_weight_SHA_verified']
MODEL=pathlib.Path(DOWNLOAD['model_path'])
assert MODEL==ROOT/'model' and ROOT.parent==pathlib.Path('/content') and ROOT.name.startswith('llama-t4-int8-')
WORK=ROOT/'inference-watchdog-fixed';WORK.mkdir(mode=0o700,exist_ok=False)
with (ROOT/'watchdog-fixed.once').open('x') as marker:marker.write('one attempt; no automatic retry')
guard=load_reviewed('fixed_watchdog','llama_watchdog.py')
cache=load_reviewed('fixed_cache_verify','cache_safe_verify.py')
# Read no shard body in the parent: advise only this fresh VM's four files,
# then sample actual headroom before the guard's first sample/spawn.
HINTS=cache.hint_exact_downloaded_shards(MODEL,ROOT/'model-manifest.json')
binding=guard.resolve_memory_cgroup(pathlib.Path('/proc/self/cgroup').read_text(),pathlib.Path('/proc/self/mountinfo').read_text())
assert binding['exact_namespace_root'] and str(binding['base'])=='/var/colab/cgroup/jupyter-children'
SAMPLE=guard.memory_sample()
assert isinstance(SAMPLE['cgroup_max_bytes'],int) and SAMPLE['cgroup_max_bytes']>0
print('__CACHE_SAFE_PREFLIGHT__'+json.dumps({'sample':SAMPLE,'hints':HINTS,'hint_effect_guaranteed':False},sort_keys=True))
assert SAMPLE['available_bytes']>=2*1024**3 and SAMPLE['cgroup_headroom_bytes']>=2*1024**3, 'cache_hint_did_not_restore_guard_headroom'
command=[str(PY),'-I','-B',str(ROOT/'llama_worker.py'),'--model',str(MODEL),'--manifest',str(ROOT/'model-manifest.json'),'--metadata',str(META),'--output',str(WORK/'result.json')]
WATCH=guard.run_owned(command,WORK,env(True),timeout_seconds=600,handshake_seconds=240,interval_seconds=.2,os_floor_bytes=2*1024**3,hard_rss_cap_bytes=8*1024**3)
print('__WATCHDOG_STATUS__'+json.dumps(WATCH,sort_keys=True))
if (WORK/'phase.json').exists():print('__PHASE_STATUS__'+(WORK/'phase.json').read_text())
assert WATCH['status']=='completed' and WATCH['gate_opened'] and WATCH['worker_returncode']==0 and WATCH['remaining_owned_count']==0
RESULT=json.loads((WORK/'result.json').read_text())
assert RESULT['status']=='single_Llama_LLM_INT8_GPU_smoke_pass' and RESULT['generation_calls']==1 and 0<RESULT['new_tokens']<=32
print('__LLAMA_RESULT__'+json.dumps(RESULT,sort_keys=True))
'''

INTRO = '''# Llama 무료 T4 INT8 — 종료 확인·결과 회수 준비본
이번 산출물은 로컬 준비·정적/합성 검증만 했습니다. 원격 실행·모델 성공을 새로 측정하지 않았습니다.

## 사용 순서와 실행 차단
첫 코드 셀은 표준 라이브러리로 내장 자료의 해시·AST·manifest만 검사하며 파일 쓰기·설치·GPU·네트워크·인증 입력을 하지 않습니다.
그 다음 설정 셀의 무료 계정/CU 미사용·무료 T4 확인, 새 실험 승인과 세 단계 허용은 모두 기본 False입니다. 현재 작업에서는 바꾸거나 실행하지 않습니다. 향후 별도 명시 승인과 공식 UI 확인이 필요하며 과거 승인을 자동 재사용하지 않습니다. 기본 Run all은 stdlib 검사 후 세 실단계를 SKIP합니다.

런타임: Python 3.12 / Torch 2.11.0+cu128 재사용·NumPy 2.0.2·Transformers 4.57.3·Accelerate 1.12.0·bitsandbytes 0.50.2 고정. T4만 사용하며 유료 CU/구독/업그레이드가 필요하거나 확인 불가하면 중단합니다. 노트북은 계정 청구 상태를 계측하거나 보장하지 않습니다. 기본 GPU 자동 선택 metadata는 없습니다.

모델: meta-llama/Llama-3.1-8B-Instruct, revision 0e9e39f249a16976918f6564b8830bc894c89659. 고정 10파일 16,069,722,669 B를 새 VM에만 받는 절차입니다. HF gated 접근/라이선스 확인은 사용자 직접, 읽기 토큰은 별도 단계 마스킹 입력 한 번만 사용하며 저장하지 않습니다. 기존 토큰·KMS·계정·DB를 읽거나 복사하지 않습니다. 참조 해제는 Python 불변 문자열의 물리적 zeroization 보장이 아닙니다. getpass 입력 대기는 timeout이 없고, echo fallback은 오류로 중단합니다. 다운로드 명목 deadline 30분/요청 connect10/read45초는 DNS·OS I/O 강제 종료 보장이 아닙니다.

## 캐시·실행 계약
준비 시작은 이전 실행의 readiness를 무효화하며 기존 파일은 보존합니다. 준비가 끝까지 성공한 경우에만 ROOT·런타임·메모리 proof·fresh timestamp·payload SHA의 context를 확정하고, 다운로드와 실행에서 동일 context를 확인합니다. 설정 셀은 허용값만 바꾸므로 단계별 checkbox 변경은 context를 유지합니다.

새 ROOT와 단일 attempt만 사용합니다. 다운로드 검증 뒤 parent의 정확 네 shard 읽기 없는 DONTNEED → 실제 OS/cgroup 여유 → child의 같은 FD chunk SHA+hint → fresh handshake/start gate → 로딩 중 정확 네 shard 주기 advisory → load 완료·generate·done 순서입니다. 힌트 효과는 보장하지 않으며 mapped active pages 강제 해제·global drop_caches는 하지 않습니다.
현재 감시기는 동일 create-time의 zombie 또는 프로세스 소멸을 관측했을 때만 최대 1초의 표본 종료 확인을 수행합니다. 실제 Popen 종료코드 확인 전에는 성공으로 처리하지 않으며 메모리·RSS·deadline·로그·알려진 자손 검사를 유지합니다. zombie root RSS는 소유권을 읽기 전후 확인해 합산합니다. 관측 identity·poll 경로·확인 표본수와 시간을 비식별 상태로 기록합니다. 표본 정책은 OS 스케줄러의 실시간 상한 보장이 아닙니다. 이전 실제 Colab의 identity 변화 원인은 미확정이며 이 수정 감시기의 실제 Colab 실행은 미검증입니다.
감시기는 저장소의 수정된 canonical 원본 바이트입니다. OS/cgroup 2 GiB floor, RSS 8 GiB cap, 0.2초 표본, 전체 600초/handshake 240초를 유지합니다. 표본 감시는 OS 메모리 상한 보장이 아닙니다. 예측 5,570,220,032 B는 controlled-experiment prediction이며 hard upper bound가 아닙니다.
원본 가중치는 보존하고 GPU Linear224개만 INT8, 나머지 FP16/parameter291 GPU·CPU/disk offload0. 합성 prompt≤64tokens, greedy 생성1회≤32newtokens/EOS와 상한 구분. 재시도/4bit/유료/모델 패치·자동 대체는 없습니다.

## 한계와 종료
마지막 결과 진단 셀은 모델을 재실행하지 않습니다. context가 없으면 고정 not_ready만 출력하고 파일도 읽지 않습니다. context·경로 결합이 유효할 때만 현재 WORK의 작은 phase·guard·result JSON과 제한된 stderr를 읽어 허용된 상태·숫자·불리언을 표시합니다. 로그·생성 원문·경로·PID·토큰은 출력하지 않습니다. 결과 표시 UI 문제가 생겨도 이 셀은 실제 모델·감시기 완료의 기록만 확인하며 실패를 성공으로 바꾸지 않습니다.
실제 새 Colab 실행·패키지 설치·GPU·출력·청취/품질·앱 통합·브라우저 표시 검증은 하지 않았습니다. 향후 승인된 실행 후 성공·실패 모두 공식 런타임 연결 해제 및 삭제, 소유 활성 세션0을 확인해야 합니다. worker 종료는 VM 연결 해제와 같지 않습니다. Drive mount·개인 경로·원본 실행 로그는 포함하지 않습니다.
'''


def code_cell(source):
    ast.parse(source)
    return dict(cell_type='code', metadata={}, execution_count=None,
                outputs=[], source=source.splitlines(keepends=True))


def phase_cell(flag, label, source):
    """Compilation is stdlib-only; disabled phases never execute their source."""
    return code_cell('LIVE_SOURCE=' + repr(source) + '\n'
                     + 'compile(LIVE_SOURCE, ' + repr(label) + ", 'exec')\n"
                     + 'if ' + flag + ':\n    exec(LIVE_SOURCE, globals())\n'
                     + 'else:\n    print(' + repr('__PHASE_SKIPPED__' + label) + ')\n')


def build_packet(original_notebook, r02_directory, watchdog_source, output_directory):
    result_helper = pinned_read(Path(__file__).with_name('file_result_check.py'), RESULT_HELPER_SHA)
    original = pinned_read(original_notebook, ORIGINAL_SHA)
    original_nb = json.loads(original)
    setup = ''.join(original_nb['cells'][1]['source'])
    payloads = ast.literal_eval(assignment(setup, 'PAYLOADS').value)
    assets = {}
    for name, record in payloads.items():
        raw = zlib.decompress(base64.b64decode(record['compressed_b64']))
        if digest(raw) != record['sha256']:
            raise ValueError('original_payload_mismatch')
        assets[name] = raw
    assets['llama_watchdog.py'] = pinned_read(watchdog_source, GUARD_SHA)
    for name, (filename, expected) in R02_INPUTS.items():
        assets[name] = pinned_read(Path(r02_directory) / filename, expected)
    worker = assets['llama_worker.py'].decode('utf-8')
    old_attempt = 'cache-safe-r02 after r01 load-stage memory-floor stop'
    if worker.count(old_attempt) != 1:
        raise ValueError('worker_provenance_not_unique')
    assets['llama_worker.py'] = worker.replace(
        old_attempt, 'fresh standalone notebook with canonical exit-fixed watchdog').encode('utf-8')
    probe = assets['llama_t4_meta.py'].decode('utf-8')
    if probe.count(OLD_GUARD_SHA) != 1:
        raise ValueError('preflight_guard_binding_not_unique')
    assets['llama_t4_meta.py'] = probe.replace(OLD_GUARD_SHA, GUARD_SHA).encode('utf-8')
    payloads = {name: dict(sha256=digest(raw), compressed_b64=base64.b64encode(
        zlib.compress(raw, 9)).decode('ascii')) for name, raw in assets.items()}
    setup = replace_assignment(setup, 'PAYLOADS', 'PAYLOADS=' + repr(payloads))
    # Strip old setup controls, including its historical True approval. The
    # separate new controls cell is the only binding of these six flags.
    setup = setup[setup.index('# Diagnostic-only'):]
    setup = RESET_RUNTIME + "assert ALLOW_RUNTIME_DOWNLOAD, 'runtime_download_disabled'\n" + (
        'assert USER_CONFIRMED_FREE_ACCOUNT_NO_PAID_CU and USER_CONFIRMED_FREE_T4 and USER_APPROVED_RUNTIME_AND_LLAMA_EXPERIMENT\n') + setup
    offline = '''# Pure stdlib: no writes, model imports, subprocess, network or credentials.
import ast,base64,hashlib,json,zlib
PAYLOADS=PAYLOAD_LITERAL
for name,item in PAYLOADS.items():
    raw=zlib.decompress(base64.b64decode(item['compressed_b64']))
    assert hashlib.sha256(raw).hexdigest()==item['sha256']
    if name.endswith('.py'):ast.parse(raw.decode('utf-8'))
manifest=json.loads(zlib.decompress(base64.b64decode(PAYLOADS['model-manifest.json']['compressed_b64'])))
assert manifest['revision']=='0e9e39f249a16976918f6564b8830bc894c89659'
assert len(manifest['files'])==10 and sum(x['size'] for x in manifest['files'])==16_069_722_669
assert PAYLOADS['llama_watchdog.py']['sha256']==GUARD_LITERAL
print('__OFFLINE_PACKET_VALIDATED__')
'''.replace('PAYLOAD_LITERAL', repr(payloads)).replace('GUARD_LITERAL', repr(GUARD_SHA))
    # The runtime references PAYLOADS defined in the pure verification cell.
    setup = replace_assignment(setup, 'PAYLOADS', "assert 'PAYLOADS' in globals()")
    setup += '\nRUNTIME_CONTEXT=' + CONTEXT_VALUE + '\n'
    cells = [dict(cell_type='markdown', metadata={}, source=INTRO.splitlines(keepends=True)),
             code_cell(offline), code_cell(CONTROLS)]
    for heading, flag, source in [('1. 런타임 준비 — 기본 건너뜀', 'ALLOW_RUNTIME_DOWNLOAD', setup),
                                 ('2. 새 VM 모델 다운로드 — 기본 건너뜀', 'ALLOW_MODEL_DOWNLOAD', DOWNLOAD),
                                 ('3. 단일 실행 — 기본 건너뜀', 'ALLOW_MODEL_EXECUTION', EXECUTE)]:
        cells.extend([dict(cell_type='markdown', metadata={}, source=['## ' + heading]), phase_cell(flag, heading, source)])
    cells.extend([dict(cell_type='markdown', metadata={}, source=['## 4. 읽기 전용 결과 확인 — 모델 재실행 없음']),
                  code_cell(result_helper.decode('utf-8')+'\nprint_file_result_check(globals())\n')])
    for index, cell in enumerate(cells):
        cell['id'] = 'watchdog-fixed-' + str(index)
    notebook = dict(nbformat=4, nbformat_minor=5, metadata={
        'kernelspec': {'name': 'python3', 'display_name': 'Python 3'},
        'language_info': {'name': 'python'}, 'colab': {'provenance': []}}, cells=cells)
    provenance = dict(original_notebook_sha256=ORIGINAL_SHA,
                      canonical_watchdog_sha256=GUARD_SHA,
                      r02_inputs={name: expected for name, (_, expected) in R02_INPUTS.items()},
                      derived_preflight_change='Only the pinned canonical watchdog SHA changed',
                      derived_worker_change='Only controlled_attempt provenance text changed from frozen r02',
                      payloads={name: dict(sha256=digest(raw), bytes=len(raw)) for name, raw in assets.items()},
                      readonly_result_helper=dict(source='scripts/colab/file_result_check.py', sha256=RESULT_HELPER_SHA,
                                                  derived_from_sha256=RESULT_HELPER_ORIGINAL_SHA,
                                                  derivation='Add fixed exit-confirmation telemetry/reason whitelist and explicit not_ready printer; no model or network code'),
                      output_disk_policy=dict(minimum_post_estimate_free_bytes=MINIMUM_FREE_BYTES,
                                              filesystem_allowance_bytes=FILESYSTEM_ALLOWANCE_BYTES),
                      validation_scope='Local static and synthetic only; no remote execution')
    out = Path(output_directory)
    if not out.is_absolute() or out.exists() or out.is_symlink():
        raise ValueError('new_absolute_output_required')
    raw_nb = (json.dumps(notebook, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    provenance['notebook'] = dict(sha256=digest(raw_nb), bytes=len(raw_nb))
    raw_provenance = (json.dumps(provenance, indent=2)+'\n').encode('utf-8')
    raw_readme = ('로컬 준비본. upload/의 노트북 하나만 전달 후보입니다.\n모든 실행 gate는 False이며 기본 실행은 stdlib 검증·live 단계 SKIP 3개·파일 읽기 없는 결과 not_ready입니다.\n새 원격 실행·설치·GPU·모델 추론·Colab 화면은 검증하지 않았습니다.\n소형 코드 packet의 실제 직렬화 크기와 파일시스템 여유분을 제외하고 최소 500GB를 보존하는 사전 검사이며 동시 외부 디스크 사용을 예약하지는 않습니다.\n').encode('utf-8')
    outputs = {'upload/'+NAME:raw_nb, 'PROVENANCE.json':raw_provenance, 'README.txt':raw_readme}
    estimated_bytes = sum(len(raw) for raw in outputs.values())+FILESYSTEM_ALLOWANCE_BYTES
    if shutil.disk_usage(out.parent).free-estimated_bytes < MINIMUM_FREE_BYTES:
        raise ValueError('C_reserve_not_met')
    out.mkdir(mode=0o700, exist_ok=False)
    (out/'upload').mkdir()
    for name, raw in outputs.items():
        with (out/name).open('xb') as output:
            output.write(raw)
    return provenance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original-notebook', required=True, type=Path)
    parser.add_argument('--r02-directory', required=True, type=Path)
    parser.add_argument('--watchdog-source', required=True, type=Path)
    parser.add_argument('--output-directory', required=True, type=Path)
    args = parser.parse_args()
    result = build_packet(**vars(args))
    print(json.dumps(result['notebook']))


if __name__ == '__main__':
    main()
