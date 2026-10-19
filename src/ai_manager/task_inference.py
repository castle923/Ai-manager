"""Typed immutable task runs with owned workers and independently validated outputs."""
import json
import math
import os
from pathlib import Path
import re
import subprocess
import threading
import time
import uuid

from . import adapters, task_contracts, task_runtime
from .inference import FileOwner, OwnedChild, digest, regular, TERMINAL
from .preparation import atomic_text, now, safe_relative

CODE_FILES=('task_inference.py','task_contracts.py','task_runtime.py','adapters.py','stt_worker.py','execution_slot.py','registry.py','server.py','desktop.py','desktop_files.py','inference.py','runtime_paths.py','runtime_reuse.py','runtime_bootstrap.py')
WORKER_ERRORS={'inference_failed','inference_out_of_memory','generation_limit_reached','output_invalid','input_changed','adapter_runtime_not_ready',
               'request_invalid','input_text_invalid','input_token_limit','model_invalid','generation_timeout','output_exists',
               'tracking_parameters_invalid','tracking_points_invalid','input_video_invalid','input_video_resource_limit','tracking_checkpoint_invalid','tracking_checkpoint_hash_mismatch','tracking_output_invalid',
               'input_prompt_invalid','input_parameters_invalid','input_path_invalid','model_configuration_invalid','runtime_version_mismatch','memory_budget_unavailable','resource_limit_reached','resource_guard_unavailable'}


def code_hashes(identifier):
    names=set(CODE_FILES)|{adapters.descriptor(identifier)['worker'],'preparation.py','config.py','security.py','external_process.py'}
    if identifier=='tapir':names.update({'tapir_safe.py','tapir_vendor/tapir_model.py','tapir_vendor/nets.py','tapir_vendor/utils.py','tapir_vendor/PROVENANCE.json'})
    if identifier=='qwen-image-2.1':names.update({'image_safe.py','image_diagnostics.py','task_resources.py'})
    if identifier=='llama-3.1-8b-instruct':names.add('task_resources.py')
    return {name:digest(Path(__file__).parent/name) for name in sorted(names)}


def read_json(path,home,maximum=131072):
    path=regular(Path(path),Path(home))
    if not 0<path.stat().st_size<=maximum:raise ValueError('record_invalid')
    with path.open('rb') as stream:data=stream.read(maximum+1)
    if len(data)>maximum:raise ValueError('record_invalid')
    def invalid(value):raise ValueError('nonfinite_record')
    return json.loads(data,parse_constant=invalid)


class TaskInference:
    def __init__(self,home,*,timeout=600,popen=subprocess.Popen):
        self.home=Path(home);self.base=regular(self.home/'task-runs',self.home);self.base.mkdir(parents=True,exist_ok=True)
        self.owner=FileOwner(self.base/'owner.lock');self.lock=threading.RLock();self.closed=threading.Event();self.wake=threading.Event()
        self.active=None;self.child=None;self.cancelled=set();self.timeout=timeout;self.popen=popen;self.thread=None
        if self.owner.handle:
            for run in self._runs():
                if run['status'] not in TERMINAL:
                    run.update(status='interrupted',error='process_interrupted',finished_at=now());self._save(run)
            self.thread=threading.Thread(target=self._loop,daemon=True);self.thread.start()

    def _path(self,identifier):
        if not isinstance(identifier,str) or not re.fullmatch('[a-f0-9]{32}',identifier):raise ValueError('run_not_found')
        return regular(self.base/identifier,self.home)

    def _save(self,run):atomic_text(self._path(run['id'])/'state.json',json.dumps(run,ensure_ascii=False,indent=2))

    def _valid(self,value):
        structural = (isinstance(value,dict) and isinstance(value.get('started_at'),str)
                and value.get('status') in TERMINAL | {'queued','preparing','loading','running','validating','cancelling'}
                and all(isinstance(value.get(k),dict) for k in ('model','input','parameters','metrics','registry_binding'))
                and isinstance(value.get('outputs'),list)
                and value.get('adapter_id') in adapters.CATALOG
                and value.get('task_type') == adapters.CATALOG[value['adapter_id']]['task_type'])
        if not structural:return False
        info=value['input'];model=value['model']
        if not all(isinstance(model.get(k),str) and model[k] for k in ('id','name','revision')):return False
        if not isinstance(info.get('sha256'),str) or not re.fullmatch('[a-f0-9]{64}',info['sha256']) or type(info.get('bytes')) is not int or info['bytes']<=0:return False
        if value['task_type']=='stt':
            duration=info.get('duration_seconds')
            if type(duration) not in (int,float) or not math.isfinite(duration) or not 0<duration<=30:return False
            if info.get('sample_rate')!=16000 or info.get('channels')!=1 or type(info.get('frames')) is not int or info['frames']/16000!=duration:return False
        for item in value['outputs']:
            if not isinstance(item,dict) or item.get('id') not in task_contracts.OUTPUTS:return False
            if any(item.get(k)!=v for k,v in task_contracts.OUTPUTS[item['id']].items()):return False
            if type(item.get('bytes')) is not int or item['bytes']<=0 or not isinstance(item.get('sha256'),str) or not re.fullmatch('[a-f0-9]{64}',item['sha256']):return False
        for key in ('total_seconds','loading_seconds','inference_seconds','peak_gpu_allocated_bytes','slot_wait_seconds'):
            item=value['metrics'].get(key)
            if item is not None and (type(item) not in (int,float) or not math.isfinite(item) or item<0):return False
        return True

    def _runs(self):
        result=[]
        for path in self.base.glob('*/state.json'):
            try:
                value=read_json(path,self.home)
                if (self._valid(value) and value['id']==path.parent.name and re.fullmatch('[a-f0-9]{32}',value['id'])):result.append(value)
            except (ValueError,OSError,KeyError,TypeError):continue
        return sorted(result,key=lambda x:x['started_at'],reverse=True)

    def get(self,identifier):
        try:
            run=read_json(self._path(identifier)/'state.json',self.home)
            if not self._valid(run) or run['id']!=identifier:raise ValueError()
            return run
        except (OSError,KeyError,ValueError,TypeError):raise ValueError('run_not_found') from None

    def public(self,run):
        result={k:run.get(k) for k in ('id','task_type','adapter_id','status','started_at','finished_at','input','parameters','error','metrics','outputs','model','registry_binding')}
        # Source locations stay in private provenance, never public run records.
        if result.get('registry_binding'):result['registry_binding']={k:v for k,v in result['registry_binding'].items() if k!='registered_source'}
        return result

    def snapshot(self):
        with self.lock:return dict(catalog=adapters.catalog(self.home),runs=[self.public(r) for r in self._runs()],active_run_id=self.active)

    def create_registered(self,payload,identifier,binding):
        item=adapters.descriptor(identifier);m=adapters.manifest(identifier)
        if not item['worker']:raise ValueError(item.get('blocker','adapter_unsupported'))
        data,info=task_contracts.decode_input(payload,item['task_type'])
        if task_runtime.environment(self.home,identifier)['status']!='ready':raise ValueError('adapter_runtime_not_ready')
        with self.lock:
            if not self.owner.handle or self.closed.is_set():raise ValueError('operation_running')
            if sum(r['status']=='queued' for r in self._runs())>=3:raise ValueError('queue_full')
            run_id=uuid.uuid4().hex;directory=self._path(run_id);directory.mkdir()
            input_name={'stt':'input.wav','tracking':'input.mp4','llm':'input.txt','image':'input.txt'}[item['task_type']]
            parameters={'stt':dict(language='ko',task='transcribe',max_new_tokens=256,seed=0,do_sample=False),'llm':dict(max_new_tokens=64,max_input_tokens=256,seed=0,do_sample=False),'tracking':dict(points=info.get('points'),max_frames=32,resize=256),'image':dict(seed=0,width=512,height=512,num_inference_steps=4,guidance_scale=4.0)}[item['task_type']]
            with (directory/input_name).open('xb') as stream:stream.write(data)
            run=dict(id=run_id,task_type=item['task_type'],adapter_id=identifier,status='queued',started_at=now(),finished_at=None,input=info,parameters=parameters,
                     model=dict(id=identifier,name=m['name'],revision=m['revision']),registry_binding=dict(binding),outputs=[],metrics={},error=None)
            atomic_text(directory/'input.json',json.dumps(dict(kind='new_run_explicit_input',**info),indent=2))
            self._save(run);self.wake.set();return self.public(run)

    def cancel(self,identifier):
        with self.lock:
            run=self.get(identifier)
            if run['status'] not in TERMINAL:
                self.cancelled.add(identifier)
                if run['status']=='queued':run.update(status='cancelled',error='cancelled',finished_at=now())
                else:run.update(status='cancelling')
                self._save(run)
            return self.public(run)

    def _check(self,identifier):
        if self.closed.is_set() or identifier in self.cancelled:raise ValueError('cancelled')

    def _prepare(self,run):
        from .registry import sha
        from .config import private_home
        directory=self._path(run['id']);identifier=run['adapter_id'];m=adapters.manifest(identifier);binding=run['registry_binding']
        if binding.get('manifest_sha256')!=digest(adapters.manifest_path(identifier)) or binding.get('asset_sha256')!=sha([{k:i[k] for k in ('path','size','sha256')} for i in m['files']]):raise ValueError('registered_artifact_mismatch')
        source=private_home(Path(binding['registered_source']));verified=[]
        for item in m['files']:
            self._check(run['id']);path=regular(source/safe_relative(item['path']),source)
            if not path.is_file() or path.stat().st_size!=item['size'] or digest(path)!=item['sha256']:raise ValueError('model_integrity_failed')
            verified.append({**item,'kind':'designated_model_component','local_path':str(path)})
        input_name={'stt':'input.wav','tracking':'input.mp4','llm':'input.txt','image':'input.txt'}[run['task_type']]
        data=regular(directory/input_name,self.home).read_bytes()
        if task_contracts.sha(data)!=run['input']['sha256'] or len(data)!=run['input']['bytes']:raise ValueError('input_changed')
        if run['task_type']=='stt' and task_contracts.wav_input(data)!=run['input']:raise ValueError('input_changed')
        python=task_runtime.python_path(self.home,identifier)
        provenance=dict(run_id=run['id'],checked_at=now(),input=run['input'],input_kind='new_run_explicit_input',inputs=verified,registry_binding=binding,manifest_sha256=digest(adapters.manifest_path(identifier)),
                        runtime=task_runtime.environment(self.home,identifier),code_sha256=code_hashes(identifier),runtime_directory=str(task_runtime.root(self.home,identifier)),offline_model_loading=True,network_firewall_claimed=False)
        atomic_text(directory/'provenance.json',json.dumps(provenance,ensure_ascii=False,indent=2))
        request=dict(run_id=run['id'],input_sha256=run['input']['sha256'],model_path=str(source),parameters=run['parameters'],input_metadata=run['input'])
        if run['task_type']=='tracking':request['model_sha256']=m['files'][0]['sha256']
        atomic_text(directory/'request.json',json.dumps(request,ensure_ascii=False))
        return python,Path(__file__).with_name(adapters.descriptor(identifier)['worker'])

    def _execute(self,run):
        child=slot=None;start=time.monotonic();waiting_start=start;slot_wait=0;directory=self._path(run['id']);last_resource_sample=0;resource_peak=0;resource_last=None;resource_min_available=None
        try:
            from .execution_slot import acquire
            self._check(run['id']);run['status']='preparing';self._save(run)
            slot=acquire(self.home,lambda:self._check(run['id']),self.closed)
            slot_wait=time.monotonic()-waiting_start;start=time.monotonic()
            python,worker=self._prepare(run);self._check(run['id'])
            env=os.environ.copy()
            for key in ('HF_TOKEN','HUGGING_FACE_HUB_TOKEN','PYTHONPATH','PYTHONHOME'):env.pop(key,None)
            env.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',DO_NOT_TRACK='1',TOKENIZERS_PARALLELISM='false',HF_HOME=str(directory/'model-cache'),HF_MODULES_CACHE=str(directory/'modules-cache'))
            with (directory/'worker.log').open('xb') as log:
                from .external_process import spawn_external
                process=spawn_external([str(python),'-I','-B',str(worker),str(directory/'request.json')],popen=self.popen,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,cwd=directory,env=env,creationflags=(subprocess.CREATE_NO_WINDOW|0x4) if os.name=='nt' else 0)
                child=OwnedChild(process);self.child=child
                while process.poll() is None:
                    self._check(run['id'])
                    if time.monotonic()-start>self.timeout:raise ValueError('inference_timeout')
                    if run['task_type'] in {'image','llm'} and time.monotonic()-last_resource_sample>=.5:
                        from .task_resources import sample,enforce
                        try:memory=sample(child)
                        except ValueError:
                            if process.poll() is not None:break
                            raise
                        resource_last=memory;resource_min_available=min(resource_min_available,memory['available_physical_bytes']) if resource_min_available is not None else memory['available_physical_bytes']
                        resource_peak=max(resource_peak,memory['peak_rss_bytes']);enforce(memory,18 if run['task_type']=='image' else 12);last_resource_sample=time.monotonic()
                    try:
                        phase=read_json(directory/'progress.json',self.home,16384)
                        if phase.get('run_id')==run['id'] and phase.get('status') in {'loading','running','validating'}:
                            with self.lock:self._check(run['id']);run['status']=phase['status'];self._save(run)
                    except (OSError,ValueError,TypeError):pass
                    self.closed.wait(.15)
                self._check(run['id'])
                try:result=read_json(directory/'result.json',self.home,65536)
                except (ValueError,OSError):raise ValueError('worker_crashed') from None
                if result.get('run_id')!=run['id'] or result.get('input_sha256')!=run['input']['sha256']:raise ValueError('worker_crashed')
                if process.returncode!=0 or result.get('status')!='generated':
                    code=result.get('error');raise ValueError(code if code in WORKER_ERRORS else 'worker_crashed')
                metrics=result.get('metrics')
                if not isinstance(metrics,dict):raise ValueError('worker_crashed')
                for key in ('loading_seconds','inference_seconds','peak_gpu_allocated_bytes'):
                    value=metrics.get(key)
                    if type(value) not in (int,float) or not math.isfinite(value) or value<0:raise ValueError('worker_crashed')
                run['status']='validating';self._save(run)
                outputs=[task_contracts.output(directory,key,self.home)[1] for key in adapters.descriptor(run['adapter_id'])['output_types']]
                if run['task_type']=='stt':
                    transcript=json.loads((directory/'transcript.json').read_text('utf8'))
                    if transcript['input_duration_seconds']!=run['input']['duration_seconds']:raise ValueError('output_invalid')
                if run['task_type']=='tracking':
                    tracking=json.loads((directory/'tracks.json').read_text('utf8'))
                    if tracking['points']!=run['input']['points'] or tracking['input_sha256']!=run['input']['sha256'] or tracking['run_id']!=run['id']:raise ValueError('output_invalid')
                    if tracking.get('model_sha256')!=adapters.manifest(run['adapter_id'])['files'][0]['sha256'] or tracking.get('vendor_revision')!='730cda1c730877cfedbe01bf87fb1cadb78a565d':raise ValueError('output_invalid')
                if run['task_type']=='image':
                    image=json.loads((directory/'image.json').read_text('utf8'))
                    if image['input_sha256']!=run['input']['sha256'] or image['prompt_sha256']!=run['input']['sha256'] or image['run_id']!=run['id'] or image['parameters']!=run['parameters']:raise ValueError('output_invalid')
                    if image.get('model_revision')!=run['model']['revision'] or image.get('diffusers_revision')!='b800f828f3951c4d206e154411bcbfa693cd322e':raise ValueError('output_invalid')
                    metrics['parent_sum_member_peak_rss_bytes']=resource_peak
                    metrics['memory_guard_rss_scope']='owned_job_members_sum_shared_pages_may_repeat'
                    metrics['memory_guard_is_os_hard_quota']=False
                if run['task_type']=='llm':
                    metrics['parent_sum_member_peak_rss_bytes']=resource_peak
                    metrics['memory_guard_rss_scope']='owned_job_members_sum_shared_pages_may_repeat'
                    metrics['memory_guard_is_os_hard_quota']=False
                with self.lock:
                    self._check(run['id']);run.update(status='succeeded',outputs=outputs,metrics=metrics,finished_at=now())
        except Exception as error:
            code=str(error);allowed=WORKER_ERRORS|{'cancelled','model_integrity_failed','inference_timeout','worker_crashed','registered_artifact_mismatch'}
            run.update(status='cancelled' if code=='cancelled' else 'failed',error=code if code in allowed else 'inference_failed',finished_at=now(),outputs=[])
        finally:
            if child:child.stop();child.close()
            if slot:slot.close()
            self.child=None
            with self.lock:
                if run['id'] in self.cancelled:run.update(status='cancelled',error='cancelled',outputs=[],finished_at=now())
                if not isinstance(run.get('metrics'),dict):run['metrics']={}
                if run['task_type'] in {'image','llm'}:
                    run['metrics'].update(parent_sum_member_peak_rss_bytes=resource_peak,memory_guard_rss_scope='owned_job_members_sum_shared_pages_may_repeat',memory_guard_is_os_hard_quota=False)
                    if resource_last is not None:run['metrics'].update(guard_last_rss_sum_bytes=resource_last['rss_bytes'],guard_min_available_physical_bytes=resource_min_available,guard_last_available_physical_bytes=resource_last['available_physical_bytes'],guard_max_rss_policy_bytes=(18 if run['task_type']=='image' else 12)*1024**3,guard_min_available_policy_bytes=3*1024**3)
                    if resource_last is not None and run.get('error')=='resource_limit_reached':
                        run['metrics']['guard_stop_conditions']=[name for name,condition in (('owned_job_rss_sum_exceeded',resource_last['rss_bytes']>(18 if run['task_type']=='image' else 12)*1024**3),('system_available_physical_below_minimum',resource_last['available_physical_bytes']<3*1024**3)) if condition]
                    if run['task_type']=='llm':
                        try:run['metrics']['placement_observation']=read_json(directory/'placement.json',self.home,16384)
                        except (OSError,ValueError):run['metrics']['placement_observation']=dict(status='not_available_loading_incomplete',actual_device_map=None)
                run['metrics']['slot_wait_seconds']=round(slot_wait if slot else time.monotonic()-waiting_start,3)
                run['metrics']['total_seconds']=round(time.monotonic()-start,3) if slot else 0.0;self._save(run)

    def _loop(self):
        while not self.closed.is_set():
            self.wake.wait(.5);self.wake.clear()
            with self.lock:
                queued=[r for r in reversed(self._runs()) if r['status']=='queued']
                if not queued:continue
                run=queued[0];self.active=run['id']
            self._execute(run)
            with self.lock:self.active=None
            self.wake.set()

    def export(self,identifier,output_id):
        with self.lock:
            run=self.get(identifier)
            if run['status']!='succeeded':raise ValueError('output_not_ready')
            data,meta=task_contracts.output(self._path(identifier),output_id,self.home)
            if meta not in run['outputs']:raise ValueError('output_invalid')
            return data,meta

    def registry_runs(self,identifier):return [self.public(r) for r in self._runs() if r.get('registry_binding',{}).get('id')==identifier]

    def registry_verified(self,run,binding):
        if run['status']!='succeeded':return False
        try:
            raw=self.get(run['id']);proof=read_json(self._path(run['id'])/'provenance.json',self.home)
            if proof['registry_binding']!=raw['registry_binding'] or proof['manifest_sha256']!=binding['manifest_sha256'] or proof['input']!=raw['input']:return False
            if proof['manifest_sha256']!=digest(adapters.manifest_path(raw['adapter_id'])):return False
            if proof['code_sha256']!=code_hashes(raw['adapter_id']):return False
            if proof['runtime']!=task_runtime.environment(self.home,raw['adapter_id']):return False
            name={'stt':'input.wav','tracking':'input.mp4','llm':'input.txt','image':'input.txt'}[raw['task_type']]
            if digest(self._path(run['id'])/name)!=run['input']['sha256']:return False
            for meta in raw['outputs']:self.export(run['id'],meta['id'])
            return bool(raw['outputs'])
        except (ValueError,OSError,KeyError):return False

    def close(self):
        self.closed.set();self.wake.set()
        if self.thread:self.thread.join(20)
        if not self.thread or not self.thread.is_alive():self.owner.close()
