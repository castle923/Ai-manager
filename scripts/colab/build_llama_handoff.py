"""Public, stdlib-only manual Colab bundle. No installs/downloads/retries."""
import argparse
import base64
from dataclasses import dataclass
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import subprocess

# Works both from the source checkout and the manually uploaded flat bundle.
HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1] if (HERE.parents[1]/'src/ai_manager/colab_contract.py').is_file() else None
CONTRACT=REPO/'src/ai_manager/colab_contract.py' if REPO else HERE/'colab_contract.py'
spec=importlib.util.spec_from_file_location('handoff_contract',CONTRACT)
contract=importlib.util.module_from_spec(spec);spec.loader.exec_module(contract)
RUNTIME=contract.RUNTIME
ENGINE=dict(generation_calls=1,quantized_linear_count=224,gpu_parameter_tensor_count=291,cpu_offload=False,disk_offload=False,model_sha_verified=True,runtime_verified=True)
SUCCESS_GUARD=dict(status='completed',reason='worker_exited',gate_opened=True,worker_returncode=0,final_worker_returncode=0,remaining_owned_count=0,cleanup_measurement_error=False)
NOT_STARTED=dict(status='not_started',reason='not_started',gate_opened=False,worker_returncode=None,final_worker_returncode=None,remaining_owned_count=0,cleanup_measurement_error=False)


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def source_pins():
    path=REPO/'src/ai_manager/colab_source_pins.json' if REPO else HERE/'colab_source_pins.json'
    return json.loads(path.read_bytes())

def verify_sources():
    pins=source_pins()
    for name,path in [('contract',CONTRACT),('worker',HERE/'llama_handoff_worker.py'),('guard',HERE/'llama_watchdog.py')]:
        if path.is_symlink() or sha(path)!=pins[name]:raise ValueError('source_mismatch')
    manifest=REPO/'src/ai_manager/adapter_manifest_llama.json' if REPO else HERE/'model-manifest.json'
    if manifest.is_symlink() or sha(manifest)!=contract.MODEL['manifest_sha256']:raise ValueError('source_mismatch')
    if not REPO:
        bundle=json.loads((HERE/'bundle-manifest.json').read_bytes())
        if sha(__file__)!=bundle['entrypoint_sha256']:raise ValueError('source_mismatch')
    return manifest

def runtime_versions(runtime_python):
    # Metadata only: never imports Torch or any model runtime package.
    code="import importlib.metadata as m,json,platform;print(json.dumps(dict(python=platform.python_version(),**{n:m.version(n) for n in "+repr(tuple(n for n in RUNTIME if n!='python'))+"})))"
    probe=subprocess.run([str(runtime_python),'-I','-B','-c',code],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10,check=False,env=child_environment())
    if probe.returncode!=0 or len(probe.stdout)>4096 or len(probe.stderr)>4096:raise ValueError('environment_unavailable')
    value=json.loads(probe.stdout)
    if type(value) is not dict or value!=RUNTIME:raise ValueError('environment_unavailable')
    return value

def child_environment(work=None):
    env={k:v for k,v in os.environ.items() if k in ('PATH','LD_LIBRARY_PATH','CUDA_VISIBLE_DEVICES','LANG','LC_ALL','SYSTEMROOT')}
    env.update(HF_ENABLE_PARALLEL_LOADING='false',HF_PARALLEL_LOADING_WORKERS='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',TOKENIZERS_PARALLELISM='false',HOME=str(work) if work else '',HF_HOME=str(work/'hf-cache') if work else '',PYTHONDONTWRITEBYTECODE='1')
    return env

def validate_model_root(model_root):
    root=Path(model_root)
    if not root.is_absolute() or root.resolve()!=root or not root.is_dir() or root.name!='model' or root.parent.parent!=Path('/content') or not root.parent.name.startswith('llama-t4-int8-'):
        raise ValueError('model_mismatch')
    return root

def select_runtime_python(model_root,runtime_python=None):
    root=validate_model_root(model_root)
    expected=root.parent/'venv'/'bin'/'python'
    selected=Path(runtime_python) if runtime_python is not None else expected
    # Only the approved model's existing sibling venv is executable. Venv python
    # itself may be a normal symlink to its base interpreter; retain its lexical
    # path so Python discovers that venv's pyvenv.cfg.
    if selected!=expected or not selected.is_absolute() or selected.parent.resolve()!=selected.parent or not selected.is_file():
        raise ValueError('environment_unavailable')
    return selected

def verify_model(model_root):
    # Parent reads no weight bodies. Full SHA verification occurs in owned child
    # with chunk DONTNEED, before any model import or handshake.
    root=validate_model_root(model_root)
    manifest=json.loads(verify_sources().read_bytes())
    for item in manifest['files']:
        path=root/item['path']
        if path.is_symlink() or not path.is_file() or path.stat().st_size!=item['size']:raise ValueError('model_mismatch')
        if item['path'].endswith('.safetensors'):
            fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
            try:os.posix_fadvise(fd,0,0,os.POSIX_FADV_DONTNEED)
            finally:os.close(fd)

@dataclass(frozen=True)
class AppContext:
    request_sha256:str
    source_sha256:tuple
    model_root:Path
    work:Path

def invoke_guard(command,work,env,**kwargs):
    spec=importlib.util.spec_from_file_location('handoff_guard',HERE/'llama_watchdog.py')
    guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
    return guard.run_owned(command,work,env,**kwargs)

def _result(request,status,stage,reason=None,guard=None,payload=None):
    value=dict(schema_version=1,request_id=request['request_id'],request_sha256=request['request_sha256'],input_sha256=request['input']['sha256'],model=request['model'],execution=request['execution'],status=status,phase={'stage':stage},guard=guard or dict(NOT_STARTED))
    if status=='success':value.update(payload)
    else:value['reason']=reason
    value['result_sha256']=contract.document_digest(value,'result_sha256')
    return contract.validate_result(value,request)

def run_request(request_bytes:bytes,model_root:Path,workspace_root:Path,approved:bool=False,*,runtime_python:Path=None)->dict:
    request=contract.parse_document(request_bytes,'request')
    # A request with different pins has no valid binding to this bundle.
    contract.validate_request(request,request['execution']['source_sha256'])
    if approved is not True:return _result(request,'stopped','preflight','approval_required')
    try:
        manifest=verify_sources()
        if request['execution']['source_sha256']!=source_pins():raise ValueError('source_mismatch')
    except Exception:return _result(request,'stopped','preflight','source_mismatch')
    root=Path(workspace_root); model=Path(model_root)
    # Neither model descendants nor a parent containing the model may be WORK.
    # Resolve existing ancestors as well, so a symlink cannot redirect writes.
    resolved_root=root.resolve();resolved_model=model.resolve()
    if resolved_root==resolved_model or resolved_root.is_relative_to(resolved_model) or resolved_model.is_relative_to(resolved_root):
        return _result(request,'stopped','preflight','model_mismatch')
    if not root.is_absolute() or root.exists() and (root.is_symlink() or root.resolve()!=root or not (root/'.app-handoff-root').is_file()):
        return _result(request,'stopped','preflight','already_started')
    work=root/request['request_id']
    if work.exists() or work.is_symlink():return _result(request,'stopped','preflight','already_started')
    try:verify_model(model)
    except Exception:return _result(request,'stopped','hashing','model_mismatch')
    try:
        selected_python=select_runtime_python(model,runtime_python)
        if runtime_versions(selected_python)!=RUNTIME:raise ValueError('runtime')
    except Exception:return _result(request,'stopped','preflight','environment_unavailable')
    context=AppContext(request['request_sha256'],tuple(sorted(source_pins().items())),model,work)
    try:
        if not root.exists():
            root.mkdir(mode=0o700);(root/'.app-handoff-root').write_text('app request workspace v1')
        work.mkdir(mode=0o700,exist_ok=False)
        with (work/'app-request.once').open('x') as f:f.write(context.request_sha256)
    except FileExistsError:return _result(request,'stopped','preflight','already_started')
    (work/'request.json').write_bytes(request_bytes)
    (work/'context.json').write_text(json.dumps(dict(request_sha256=context.request_sha256,source_sha256=dict(context.source_sha256),model_root=str(model),work=str(work))))
    env=child_environment(work)
    command=[str(selected_python),'-I','-B',str(HERE/'llama_handoff_worker.py'),'--model',str(model),'--manifest',str(manifest),'--request',str(work/'request.json'),'--context',str(work/'context.json'),'--output',str(work/'worker-result.json')]
    try:
        summary=invoke_guard(command,work,env,timeout_seconds=600,handshake_seconds=240,interval_seconds=.2,os_floor_bytes=2*1024**3,hard_rss_cap_bytes=8*1024**3,log_limit_bytes=256*1024)
    except Exception:return _result(request,'failure','loading','worker_failed')
    clean=summary.get('remaining_owned_count')==0 and summary.get('cleanup_measurement_error') is False
    guard={k:summary.get(k) for k in SUCCESS_GUARD}
    guard['status']='completed' if summary.get('status')=='completed' else 'stopped'
    guard['reason']='worker_exited' if guard['status']=='completed' else 'guard_stopped'
    if not clean:
        guard['reason']='cleanup_failed'
        return _result(request,'failure','loading','cleanup_failed',guard)
    if guard!=SUCCESS_GUARD:
        reason='worker_failed' if summary.get('worker_returncode') not in (None,0) else 'guard_stopped'
        guard['reason']=reason
        return _result(request,'failure' if reason=='worker_failed' else 'stopped','loading',reason,guard)
    try:
        path=work/'worker-result.json'
        if path.is_symlink() or path.stat().st_size>65536:raise ValueError('output')
        payload=contract.parse_document(path.read_bytes(),'result')
        if payload.get('reason') in ('input_token_limit','model_mismatch'):
            return _result(request,'stopped','hashing',payload['reason'],guard)
        if set(payload)!={'response','engine'}:raise ValueError('output')
        return _result(request,'success','done',guard=guard,payload=payload)
    except Exception:return _result(request,'failure','generating','output_invalid',guard)

def build_bundle(output:Path)->dict:
    output=Path(output)
    if not output.is_absolute() or output.exists() or output.is_symlink():raise ValueError('new_absolute_output_required')
    manifest=verify_sources();pins=source_pins()
    assets={'colab_contract.py':CONTRACT.read_bytes(),'llama_handoff_worker.py':(HERE/'llama_handoff_worker.py').read_bytes(),'llama_watchdog.py':(HERE/'llama_watchdog.py').read_bytes(),'model-manifest.json':manifest.read_bytes(),'colab_source_pins.json':json.dumps(pins,sort_keys=True).encode(),'build_llama_handoff.py':Path(__file__).read_bytes()}
    info=dict(source_sha256=pins,entrypoint_sha256=sha(__file__),files={k:{'sha256':hashlib.sha256(v).hexdigest(),'bytes':len(v)} for k,v in assets.items()})
    assets['bundle-manifest.json']=json.dumps(info,sort_keys=True).encode()
    payload={k:base64.b64encode(v).decode() for k,v in assets.items()}
    setup="import base64,hashlib,json,pathlib,uuid,importlib.util\nHANDOFF_PAYLOAD="+repr(payload)+"\nfor name,encoded in HANDOFF_PAYLOAD.items():\n raw=base64.b64decode(encoded)\n if name!='bundle-manifest.json':\n  expected=json.loads(base64.b64decode(HANDOFF_PAYLOAD['bundle-manifest.json']))['files'][name]['sha256']\n  assert hashlib.sha256(raw).hexdigest()==expected\nprint('Public source bundle verified; execution approval defaults to False.')\n"
    run="APPROVE_ONE_REQUEST=False # Review this request and free T4 environment before changing.\nREQUEST_PATH='' # Manually upload request JSON using Colab Files.\nMODEL_ROOT='' # Existing verified /content/llama-t4-int8-*/model only; sibling venv reused.\nif APPROVE_ONE_REQUEST:\n import types,sys\n request_raw=pathlib.Path(REQUEST_PATH).read_bytes()\n request_contract=types.ModuleType('app_request_contract')\n exec(compile(base64.b64decode(HANDOFF_PAYLOAD['colab_contract.py']),'colab_contract.py','exec'),request_contract.__dict__)\n request_pins=json.loads(base64.b64decode(HANDOFF_PAYLOAD['colab_source_pins.json']))\n app_request=request_contract.validate_request(request_contract.parse_document(request_raw,'request'),request_pins)\n app_request_id=app_request['request_id']\n if 'APP_HANDOFF_CONTEXTS' not in globals():APP_HANDOFF_CONTEXTS={}\n if app_request_id in APP_HANDOFF_CONTEXTS:raise RuntimeError('already_started')\n app_current_context=pathlib.Path('/content')/('llama-app-handoff-'+uuid.uuid4().hex)\n APP_HANDOFF_CONTEXTS[app_request_id]=app_current_context\n app_current_context.mkdir(mode=0o700)\n for name,encoded in HANDOFF_PAYLOAD.items():(app_current_context/name).write_bytes(base64.b64decode(encoded))\n spec=importlib.util.spec_from_file_location('app_request_bridge',app_current_context/'build_llama_handoff.py')\n bridge=importlib.util.module_from_spec(spec)\n sys.modules[spec.name]=bridge\n spec.loader.exec_module(bridge)\n report=bridge.run_request(request_raw,pathlib.Path(MODEL_ROOT),app_current_context/'requests',approved=True)\n result_path=app_current_context/(app_request_id+'.result.json')\n with result_path.open('x',encoding='utf-8') as result_file:json.dump(report,result_file,ensure_ascii=False)\n print('Result saved as '+result_path.name+'. Download with Colab Files. No retry for this UUID.')\nelse:print('Execution skipped; no model imports or reads.')\n"
    cells=[dict(cell_type='markdown',metadata={},source=['# Manual Llama app request\nUpload this notebook and one request JSON manually. Use only an existing reviewed free T4 VM and model. No installs, downloads, Drive mount, API server or retry. The result is an external report, not remote attestation. Existing ROOT/WORK and markers are preserved. Preserve the existing model cache and runtime for another new request UUID. Stop active generation after collecting the result; runtime deletion is a separate user decision and may remove the cached model.']),dict(cell_type='code',metadata={},execution_count=None,outputs=[],source=setup.splitlines(True)),dict(cell_type='code',metadata={},execution_count=None,outputs=[],source=run.splitlines(True))]
    assets['Llama_App_Request.ipynb']=json.dumps(dict(nbformat=4,nbformat_minor=5,metadata={'kernelspec':{'name':'python3','display_name':'Python 3'}},cells=cells),ensure_ascii=False).encode()
    size=sum(map(len,assets.values()))
    if shutil.disk_usage(output.parent).free-size-1024**2<500_000_000_000:raise ValueError('C_reserve_not_met')
    output.mkdir(mode=0o700)
    for name,raw in assets.items():
        with (output/name).open('xb') as f:f.write(raw)
    info['notebook']=dict(name='Llama_App_Request.ipynb',sha256=hashlib.sha256(assets['Llama_App_Request.ipynb']).hexdigest(),bytes=len(assets['Llama_App_Request.ipynb']))
    return info

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    print(json.dumps(build_bundle(parser.parse_args().output),sort_keys=True))
