"""Separate, explicitly prepared adapter environment. Never modifies the TTS runtime."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import threading
import time
import uuid

VERSIONS={'torch':'2.9.1+cu128','transformers':'4.57.3','numpy':'2.2.6','safetensors':'0.8.0','tokenizers':'0.22.2'}
LOCKS={'whisper-large-v3-turbo':'requirements_stt.lock','tapir':'requirements_tracking.lock','llama-3.1-8b-instruct':'requirements_llm.lock','qwen-image-2.1':'requirements_image.lock'}


def versions(identifier):
    if identifier=='whisper-large-v3-turbo':return dict(VERSIONS)
    if identifier=='tapir':return {'torch':'2.9.1+cu128','numpy':'2.2.6','Pillow':'11.3.0','av':'16.0.1','dm-tree':'0.1.9','einshape':'1.0'}
    if identifier=='llama-3.1-8b-instruct':return dict(VERSIONS,accelerate='1.12.0',psutil='7.1.3')
    if identifier=='qwen-image-2.1':return {'torch':'2.9.1+cu128','torchvision':'0.24.1+cu128','transformers':'5.17.0','accelerate':'1.12.0','safetensors':'0.8.0','Pillow':'11.3.0','psutil':'7.2.2','diffusers_git_revision':'b800f828f3951c4d206e154411bcbfa693cd322e','pipeline_source_sha256':'e75e4ce38d38e194edaac818bba99b2115b4bb2bfdbd15ce03a2813b0fe8856c'}
    raise ValueError('adapter_runtime_unsupported')


def requirements(identifier):
    if identifier not in LOCKS:raise ValueError('adapter_runtime_unsupported')
    return Path(__file__).with_name(LOCKS[identifier])


def root(home,identifier):
    from .adapters import descriptor
    from .inference import regular
    descriptor(identifier)
    from .runtime_paths import adapter_runtime_root
    return regular(adapter_runtime_root(home,identifier),Path(home))


def environment(home,identifier):
    from .inference import regular, digest
    directory=root(home,identifier)
    try:
        record=json.loads(regular(directory/'environment.json',Path(home)).read_text('utf8'))
        python=regular(directory/'venv'/'Scripts'/'python.exe',Path(home))
        lock=regular(directory/'requirements.lock',Path(home))
        if record.get('adapter_id')!=identifier or record.get('status')!='ready' or not python.is_file() or record.get('lock_sha256')!=digest(lock) or digest(lock)!=digest(requirements(identifier)) or record.get('packages')!=versions(identifier) or not record.get('cuda_available'):
            raise ValueError()
        if record.get('setup_inputs_sha256') is not None and record['setup_inputs_sha256']!=digest(regular(directory/'setup-inputs.json',Path(home))):raise ValueError()
        if record.get('resolved_packages_sha256') is not None and record['resolved_packages_sha256']!=digest(regular(directory/'installed-packages.json',Path(home))):raise ValueError()
        return {key:record[key] for key in ('status','adapter_id','checked_at','python','packages','cuda_available','device','lock_sha256','setup_inputs_sha256','resolved_packages_sha256') if key in record}
    except (ValueError,OSError,KeyError,TypeError,AttributeError):
        return dict(status='unverified',blockers=['adapter_runtime_not_ready'])


def python_path(home,identifier):
    if environment(home,identifier)['status']!='ready': raise ValueError('adapter_runtime_not_ready')
    return root(home,identifier)/'venv'/'Scripts'/'python.exe'


class RuntimeSetup:
    """User-triggered environment setup, owning only its fresh venv children."""
    def __init__(self,home,base_python,resources=None):
        self.home=Path(home);self.base_python=Path(base_python)
        self.resources=Path(resources) if resources is not None else None
        self.closed=threading.Event();self.thread=None;self.child=None
        self.admission=threading.Lock()
        self.state=dict(status='not_started',stage='awaiting_user')

    def snapshot(self,identifier='whisper-large-v3-turbo'):
        if environment(self.home,identifier)['status']=='ready':return dict(status='ready',stage='ready',adapter_id=identifier)
        if self.state.get('adapter_id')==identifier:return dict(self.state)
        return dict(status='not_started',stage='awaiting_user',adapter_id=identifier)

    def start(self,identifier='whisper-large-v3-turbo'):
        if identifier not in LOCKS:return dict(status='failed',error='adapter_runtime_unsupported')
        if environment(self.home,identifier)['status']=='ready':return dict(status='ready',stage='ready',adapter_id=identifier)
        with self.admission:
            if self.thread and self.thread.is_alive():return dict(self.state)
            if self.closed.is_set():return dict(status='failed',error='runtime_closed')
            self.state=dict(status='running',stage='creating_adapter_environment',adapter_id=identifier)
            self.thread=threading.Thread(target=self._prepare,args=(identifier,),daemon=True);self.thread.start()
            return self.snapshot(identifier)

    def _run(self,args,log):
        from .external_process import spawn_external
        from .inference import OwnedChild
        env=os.environ.copy()
        for key in ('PYTHONPATH','PYTHONHOME','HF_TOKEN','HUGGING_FACE_HUB_TOKEN'):env.pop(key,None)
        # -I ignores PYTHONDONTWRITEBYTECODE; preserve the bundled base's pinned pyc bytes.
        process=spawn_external([str(args[0]),'-B',*[str(a) for a in args[1:]]],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,env=env,creationflags=(subprocess.CREATE_NO_WINDOW|0x4) if os.name=='nt' else 0)
        child=OwnedChild(process);self.child=child
        try:
            while process.poll() is None:
                if self.closed.wait(.2):raise ValueError('runtime_setup_cancelled')
            if process.returncode!=0:raise ValueError('runtime_install_failed')
        finally:
            child.stop();child.close();self.child=None

    def _prepare(self,identifier):
        from .inference import FileOwner,digest,regular
        from .preparation import atomic_text,now
        owner=None
        try:
            directory=root(self.home,identifier);directory.mkdir(parents=True,exist_ok=True)
            owner=FileOwner(directory/'setup.lock')
            if not owner.handle:raise ValueError('runtime_setup_already_owned')
            requirements_file=requirements(identifier)
            marker=regular(directory/'setup-inputs.json',self.home)
            base_python=self.base_python
            if identifier=='qwen-image-2.1' and self.resources is not None:base_python=self.resources/'python_image_runtime'/'python.exe'
            from .runtime_paths import python_base
            base_python=python_base(self.home,identifier,base_python.parent)/'python.exe'
            expected=dict(base_python_path=str(base_python.resolve()),base_python_sha256=digest(base_python),requirements_sha256=digest(requirements_file),adapter_id=identifier)
            if self.resources is not None:
                from .config import private_home
                image=identifier=='qwen-image-2.1'
                base=python_base(self.home,identifier,self.resources/('python_image_runtime' if image else 'python_runtime'))
                metadata=json.loads(private_home(self.resources/('python-image-runtime.json' if image else 'python-runtime.json')).read_text('utf8'))
                if private_home(base_python)!=base/'python.exe':raise ValueError('bundled_python_integrity_failed')
                actual={p.relative_to(base).as_posix() for p in base.rglob('*') if p.is_file()}
                if actual!=set(metadata['files']):raise ValueError('bundled_python_integrity_failed')
                for relative,pin in metadata['files'].items():
                    component=private_home(base/relative)
                    if not component.is_relative_to(base) or digest(component)!=pin:raise ValueError('bundled_python_integrity_failed')
                expected.update(python_base_kind='verified_bundled_python',python_archive_sha256=metadata['archive_sha256'])
            else:expected['python_base_kind']='explicit_development_python_base_not_final_package_proof'
            venv=regular(directory/'venv',self.home)
            longest=venv/'Lib'/'site-packages'/'torch'/'lib'/'cudnn_engines_precompiled64_9.dll'
            if os.name=='nt' and len(str(longest.resolve()))>=260:raise ValueError('runtime_path_too_long_use_short_home')
            if marker.exists():
                if json.loads(marker.read_text('utf8'))!=expected:raise ValueError('runtime_inputs_changed_use_new_home')
            else:
                if venv.exists():raise ValueError('runtime_existing_environment_unowned')
                with marker.open('x',encoding='utf8') as stream:json.dump(expected,stream)
            with regular(directory/'setup.log',self.home).open('ab') as log:
                if not (venv/'Scripts'/'python.exe').is_file():self._run([base_python,'-I','-m','venv',venv],log)
                python=venv/'Scripts'/'python.exe'
                self.state.update(stage='installing_adapter_dependencies')
                self._run([python,'-I','-m','pip','install','--index-url','https://pypi.org/simple','pip==26.2.1'],log)
                self._run([python,'-I','-m','pip','install','--only-binary=:all:','--index-url','https://download.pytorch.org/whl/cu128','--extra-index-url','https://pypi.org/simple','torch==2.9.1+cu128'],log)
                self._run([python,'-I','-m','pip','install','--index-url','https://pypi.org/simple','-r',requirements_file],log)
                self._run([python,'-I','-m','pip','check'],log)
            # Preserve exact source lock bytes; text newline conversion changes its pin.
            temporary=directory/(uuid.uuid4().hex+'.lock.partial')
            temporary.write_bytes(requirements_file.read_bytes());os.replace(temporary,directory/'requirements.lock')
            # Probe the newly installed environment; never reuse a previous probe result.
            probe=directory/'probe.json'
            imports={'whisper-large-v3-turbo':'import transformers,numpy,safetensors,tokenizers','tapir':'import av,numpy,PIL,tree,einshape','llama-3.1-8b-instruct':'import transformers,numpy,safetensors,tokenizers,accelerate,psutil','qwen-image-2.1':'import transformers,diffusers,safetensors,accelerate,PIL,psutil'}[identifier]
            packages="{n:importlib.metadata.version(n) for n in "+repr(tuple(versions(identifier)))+"}"
            if identifier=='qwen-image-2.1':
                imports+="; import sys; sys.path.insert(0,"+repr(str(Path(__file__).resolve().parent.parent))+"); from ai_manager.image_worker import check_runtime"
                packages='check_runtime()'
            installed=directory/'installed-packages.json'
            script="import torch,importlib.metadata,json,pathlib,platform; "+imports+"; value=dict(python=platform.python_version(),packages="+packages+",cuda_available=torch.cuda.is_available(),device=torch.cuda.get_device_name(0) if torch.cuda.is_available() else None); pathlib.Path("+repr(str(installed))+").write_text(json.dumps({d.metadata['Name']:d.version for d in importlib.metadata.distributions()},sort_keys=True,indent=2),'utf8'); pathlib.Path("+repr(str(probe))+").write_text(json.dumps(value),'utf8')"
            with (directory/'setup.log').open('ab') as log:self._run([python,'-I','-c',script],log)
            result=json.loads(probe.read_text('utf8'))
            if result['packages']!=versions(identifier) or not result['cuda_available']:raise ValueError('adapter_runtime_probe_failed')
            result.update(status='ready',adapter_id=identifier,checked_at=now(),lock_sha256=digest(directory/'requirements.lock'),setup_inputs_sha256=digest(marker),resolved_packages_sha256=digest(installed))
            atomic_text(directory/'environment.json',json.dumps(result,indent=2))
            if environment(self.home,identifier)['status']!='ready':raise ValueError('adapter_runtime_probe_failed')
            self.state.update(status='ready',stage='ready')
        except Exception as error:
            allowed={'runtime_setup_cancelled','runtime_install_failed','runtime_setup_already_owned','runtime_inputs_changed_use_new_home','runtime_existing_environment_unowned','adapter_runtime_probe_failed','runtime_path_too_long_use_short_home','bundled_python_integrity_failed'}
            self.state.update(status='failed',error=str(error) if str(error) in allowed else 'adapter_runtime_setup_failed')
        finally:
            if owner:owner.close()

    def close(self):
        self.closed.set()
        if self.thread:self.thread.join(20)
