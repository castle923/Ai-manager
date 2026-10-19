"""M13 bounded offline model bridge. Only fixed project workers, never supplied code."""
import hashlib
import io
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import time
import wave
from .validation_contracts import fail, integer, object_fields
from .validation_intake import safe_path, signature, manifest_table, observation_sha, metadata_json
from .inference import DEFAULTS, OwnedChild, digest, validate_wav, regular
from .preparation import atomic_text
from . import adapters, task_contracts, task_runtime

TTS_PACKAGES={'qwen-tts':'0.1.1','torch':'2.9.1+cu128','torchaudio':'2.9.1+cu128',
              'transformers':'4.57.3','accelerate':'1.12.0','soundfile':'0.14.0','onnxruntime':'1.23.2','sox':'1.5.0'}


def observe_scopes(roots):
    """Explicit bounded local roots only; enables a fresh TTS→STT batch graph."""
    from .validation_intake import observe_local
    if type(roots) is not list or not 1<=len(roots)<=6:fail('model_scope_count_invalid')
    observations=[observe_local(root,depth_limit=2,json_limit=262144,read_limit=524288,metadata_anchors_only=True) for root in roots]
    return _compose_scopes(observations)


def _compose_scopes(observations):
    identities=[o['source_identity'] for o in observations]
    if len(set(identities))!=len(identities):fail('model_scope_duplicate')
    candidates=[]
    for index,observation in enumerate(observations):
        if not observation['complete']:fail('source_not_dispatchable')
        for c in observation['candidates']:
            candidate=dict(c,source_index=index)
            hints=c.get('weak_hints',[])
            if c['identity']=='unknown' and len(hints)==1 and hints[0]['profile_id']=='tapir':
                candidate.update(profile_id='tapir',identity='manifest_hash_required')
            candidates.append(candidate)
    if len({c['profile_id'] for c in candidates})!=len(candidates):fail('model_profile_duplicate')
    value=dict(kind='local_model_scopes',complete=True,observations=observations,candidates=candidates,
        source_identity=observation_sha(identities),read_bytes=sum(o['read_bytes'] for o in observations),
        scope=dict(read_limit=sum(o['scope']['read_limit'] for o in observations)))
    value['fingerprint']=observation_sha([o['fingerprint'] for o in observations]);return value


def reobserve_scopes(observation):
    from .validation_intake import reobserve
    current=_compose_scopes([reobserve(source) for source in observation['observations']])
    if any(current[k]!=observation[k] for k in ('fingerprint','candidates','source_identity','scope','read_bytes','complete')):fail('source_stale')
    return observation


def full_hash(root, manifest, check=lambda:None,progress=lambda item:None):
    """Hash every required byte with bounded chunks and ancestor/file identity checks."""
    result=[]
    for item in manifest['files']:
        check();path,pins=safe_path(root,item['path'],_with_identity=True);before=path.stat()
        if not path.is_file() or before.st_size!=item['size']:fail('model_integrity_failed')
        h=hashlib.sha256();count=0
        with os.fdopen(os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)),'rb') as stream:
            if signature(os.fstat(stream.fileno()))!=signature(before) or safe_path(root,item['path'],_with_identity=True)[1]!=pins:fail('source_changed')
            while True:
                check();chunk=stream.read(1048576)
                if not chunk:break
                count+=len(chunk)
                if count>item['size']:fail('source_changed')
                h.update(chunk)
            after=os.fstat(stream.fileno())
        if safe_path(root,item['path'],_with_identity=True)[1]!=pins or signature(after)!=signature(before) or signature(path.stat())!=signature(before):fail('source_changed')
        if count!=item['size'] or h.hexdigest()!=item['sha256']:fail('model_integrity_failed')
        result.append(dict(path=item['path'],bytes=count,sha256=h.hexdigest(),signature=signature(before),parents=pins))
        progress(result[-1])
    return result


def runtime_binding(python, lock, profile):
    python=safe_path(Path(python));lock=safe_path(Path(lock))
    if not python.is_file() or not lock.is_file():fail('runtime_not_ready')
    packaged=Path(__file__).with_name('requirements-runtime.lock') if profile.startswith('qwen3-tts-') else task_runtime.requirements(profile)
    # TTS historical lock name is requirements.lock in source distributions.
    if not packaged.exists() and profile.startswith('qwen3-tts-'):packaged=Path(__file__).parents[2]/'requirements-runtime.lock'
    # Windows-generated adapter locks may use CRLF; accept only this exact EOL
    # equivalence. Persist and recheck the actual raw lock SHA independently.
    if lock.read_bytes().replace(b'\r\n',b'\n')!=packaged.read_bytes().replace(b'\r\n',b'\n'):fail('runtime_lock_mismatch')
    return dict(python=str(python),python_sha256=digest(python),lock=str(lock),lock_sha256=digest(lock),
                packaged_lock_sha256=digest(packaged),canonical_lock_sha256=hashlib.sha256(lock.read_bytes().replace(b'\r\n',b'\n')).hexdigest(),lock_equivalence_policy='crlf_lf_only',
                packages=TTS_PACKAGES if profile.startswith('qwen3-tts-') else task_runtime.versions(profile))


def check_binding(binding, profile):
    if runtime_binding(binding['python'],binding['lock'],profile)!=binding:fail('runtime_changed')


def make_spec(observation, runtimes, shared_home, *, timeout_seconds=600, hash_seconds=300):
    if observation.get('kind') not in ('local_readonly','local_model_scopes'):fail('model_local_source_required')
    safe_path(Path(shared_home));integer(timeout_seconds,1,900);integer(hash_seconds,1,600)
    candidates={c['candidate_id']:c for c in observation['candidates']}
    if set(runtimes)-{c['profile_id'] for c in candidates.values()}:fail('runtime_profile_unknown')
    values={}
    for profile,value in runtimes.items():
        object_fields(value,('python','lock'));values[profile]=runtime_binding(value['python'],value['lock'],profile)
    # Artifact verification is intentionally performed at dispatch under the shared slot.
    # No initial hash proof is claimed by merely creating or approving a plan.
    return dict(version=1,runtimes=values,shared_home=str(Path(shared_home)),timeout_seconds=timeout_seconds,
                hash_seconds=hash_seconds,fixture_recipe='m13-fresh-v1',hash_bytes=2*sum(manifest_table()[2][c['profile_id']]['files'][i]['size']
                    for c in candidates.values() if c['profile_id'] in manifest_table()[2]
                    for i in range(len(manifest_table()[2][c['profile_id']]['files']))))


def check_spec(spec, observation):
    object_fields(spec,('version','runtimes','shared_home','timeout_seconds','hash_seconds','fixture_recipe','hash_bytes'))
    if spec.get('version')!=1 or spec.get('fixture_recipe')!='m13-fresh-v1':fail('model_spec_invalid')
    integer(spec['hash_bytes'],0,128*1024**3)
    for profile,binding in spec['runtimes'].items():check_binding(binding,profile)
    original={p:dict(python=b['python'],lock=b['lock']) for p,b in spec['runtimes'].items()}
    if make_spec(observation,original,spec['shared_home'],timeout_seconds=spec['timeout_seconds'],hash_seconds=spec['hash_seconds'])!=spec:fail('model_spec_invalid')


def drain_child(child):
    """Terminate this exact Job and observe ActiveProcesses=0 before releasing its slot."""
    if os.name!='nt' or not child.job:fail('child_cleanup_unverified')
    import ctypes
    from ctypes import wintypes
    class Accounting(ctypes.Structure):
        _fields_=[(name,ctypes.c_int64) for name in ('user','kernel','period_user','period_kernel')]+[(name,wintypes.DWORD) for name in ('faults','total','active','terminated')]
    kernel=child.kernel
    kernel.TerminateJobObject.argtypes=[wintypes.HANDLE,wintypes.UINT]
    kernel.QueryInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD,ctypes.c_void_p]
    if not kernel.TerminateJobObject(child.job,1):fail('child_cleanup_unverified')
    deadline=time.monotonic()+15
    while True:
        info=Accounting()
        if not kernel.QueryInformationJobObject(child.job,1,ctypes.byref(info),ctypes.sizeof(info),None):fail('child_cleanup_unverified')
        if info.active==0:break
        if time.monotonic()>=deadline:fail('child_cleanup_unverified')
        time.sleep(.03)
    child.stop()


def _owned(command,directory,check,closed,timeout,*,log_name,resource_gib=None):
    """Always wait/close owned child before returning or allowing another case."""
    from .external_process import spawn_external
    child=None;process=None;start=time.monotonic()
    env={k:v for k,v in os.environ.items() if k.upper() not in {'PYTHONPATH','PYTHONHOME','HF_TOKEN','HUGGING_FACE_HUB_TOKEN'}}
    env.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_DATASETS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',DO_NOT_TRACK='1',
               TOKENIZERS_PARALLELISM='false',HF_HOME=str(directory/'model-cache'),HF_MODULES_CACHE=str(directory/'modules-cache'))
    with (directory/log_name).open('xb') as log:
        from .validation_recovery import spawn_marker,mark_job
        marker,job=spawn_marker(directory,log_name)
        try:
            check();process=spawn_external(command,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,cwd=directory,env=env,
                creationflags=(subprocess.CREATE_NO_WINDOW|0x4) if os.name=='nt' else 0)
            child=OwnedChild(process,job_name=job['name'])
            mark_job(marker,job,'owned')
            sampled=0
            while process.poll() is None:
                check()
                if time.monotonic()-start>timeout:fail('timed_out')
                if resource_gib and time.monotonic()-sampled>=.5:
                    from .task_resources import sample,enforce
                    try:enforce(sample(child),resource_gib)
                    except ValueError:
                        if process.poll() is None:fail('resource_guard_blocked')
                    sampled=time.monotonic()
                closed.wait(.1)
            check();return process.returncode
        finally:
            if child:
                try:
                    drain_child(child)
                    mark_job(marker,job,'drained')
                    atomic_text(directory/(log_name+'.ownership.json'),json.dumps(dict(pid=process.pid,exit_code=process.returncode,job_active_processes=0,owned_cleanup_verified=True)))
                finally:child.close()
            if process is not None and process.poll() is None:process.kill();process.wait(timeout=5)


def preflight(binding, profile, directory, check, closed,*,log_name='environment.log'):
    check_binding(binding,profile)
    script=Path(__file__).with_name('validation_env_probe.py')
    code=_owned([binding['python'],'-I','-B',str(script),json.dumps(list(binding['packages'])),str(directory)],
                directory,check,closed,60,log_name=log_name)
    if code:fail('environment_probe_failed')
    raw=(directory/log_name).read_bytes()
    if len(raw)>65536:fail('environment_probe_failed')
    try:value=metadata_json(raw.strip().splitlines()[-1],maximum=65536)
    except (IndexError,ValueError):fail('environment_probe_failed')
    if value['packages']!=binding['packages'] or not value['cuda_available']:fail('environment_not_ready')
    required_gpu=3*1024**3 if profile.startswith('qwen3-tts-') else {'whisper-large-v3-turbo':2,'tapir':2,'llama-3.1-8b-instruct':18,'qwen-image-2.1':24}[profile]*1024**3
    if value['ram_available_bytes']<3*1024**3 or value['gpu_free_bytes']<required_gpu or value['disk_free_bytes']<512*1024**2:fail('resource_blocked')
    return dict(observation=value,policy=dict(min_ram_bytes=3*1024**3,min_gpu_free_bytes=required_gpu,min_disk_bytes=512*1024**2),ready=True)


def fresh_input(profile,batch,case,directory,dependency=None):
    text='안녕하세요. 오늘은 새로운 모델 검수 문장을 읽습니다.'
    # The approved recipe fixes common TTS conditions. Bytes are newly written per run.
    lineage=dict(batch_id=batch,case_id=case,recipe='m13-fresh-v1',seed=0)
    if profile=='whisper-large-v3-turbo':
        if dependency is None:fail('deferred_dependency')
        if dependency.get('batch_id')!=batch:fail('dependency_batch_mismatch')
        source=Path(dependency['directory'])/'output.wav'
        validate_wav(source)
        if digest(source)!=dependency['outputs'][0]['sha256']:fail('dependency_changed')
        with wave.open(str(source),'rb') as r:
            rate=r.getframerate();frames=r.readframes(r.getnframes())
        samples=struct.unpack('<'+'h'*(len(frames)//2),frames);count=int(len(samples)*16000/rate)
        # Deterministic linear interpolation from this batch's PCM16 mono TTS only.
        output=[]
        for n in range(count):
            pos=n*rate/16000;lo=int(pos);f=pos-lo
            output.append(round(samples[lo]*(1-f)+samples[min(lo+1,len(samples)-1)]*f))
        buffer=io.BytesIO()
        with wave.open(buffer,'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(struct.pack('<'+'h'*len(output),*output))
        data=buffer.getvalue();info=task_contracts.wav_input(data);name='input.wav'
        lineage.update(source_case=dependency['case_id'],source_run=dependency['run_id'],source_sha256=digest(source),transform='pcm16-linear-mono-16000-v1')
    elif profile=='tapir':
        data=(directory/'input.mp4').read_bytes()
        import base64
        data,info=task_contracts.decode_input(dict(video_base64=base64.b64encode(data).decode(),points=[dict(x=.25,y=.5)]),'tracking')
        name='input.mp4'
    else:
        if profile=='qwen-image-2.1':text='A blue ceramic cup on a wooden desk in soft daylight.'
        elif profile=='llama-3.1-8b-instruct':text='한국어로 짧게 답하세요. 물이 얼면 무엇이 되나요?'
        data=text.encode('utf8');info=dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest());name='input.txt'
    if profile!='tapir':
        with (directory/name).open('xb') as stream:stream.write(data)
    lineage.update(input=info);atomic_text(directory/'lineage.json',json.dumps(lineage,ensure_ascii=False))
    return data,info,lineage


def validate_outputs(profile,directory,request,result,returncode):
    if returncode!=0 or result.get('status')!='generated' or result.get('run_id')!=request['run_id'] or result.get('input_sha256')!=request['input_sha256']:fail('worker_failed')
    metrics=result.get('metrics')
    if not isinstance(metrics,dict):fail('output_invalid')
    for key in ('loading_seconds','inference_seconds','peak_gpu_allocated_bytes'):
        value=metrics.get(key)
        if type(value) not in (int,float) or not math.isfinite(value) or value<0:fail('output_invalid')
    if profile.startswith('qwen3-tts-'):
        if metrics.get('eos_reached') is not True:fail('output_invalid')
        meta=validate_wav(regular(directory/'output.wav',directory));return [dict(id='audio',**meta)]
    outputs=[task_contracts.output(directory,key,directory)[1] for key in adapters.descriptor(profile)['output_types']]
    if profile=='whisper-large-v3-turbo':
        value=json.loads((directory/'transcript.json').read_text('utf8'))
        if value['input_duration_seconds']!=request['input_metadata']['duration_seconds']:fail('output_invalid')
    elif profile=='qwen-image-2.1':
        value=json.loads((directory/'image.json').read_text('utf8'))
        if any(value.get(k)!=v for k,v in dict(run_id=request['run_id'],input_sha256=request['input_sha256'],prompt_sha256=request['input_sha256'],parameters=request['parameters'],model_revision=manifest_table()[2][profile]['revision'],diffusers_revision='b800f828f3951c4d206e154411bcbfa693cd322e').items()):fail('output_invalid')
    elif profile=='tapir':
        value=json.loads((directory/'tracks.json').read_text('utf8'))
        if any(value.get(k)!=v for k,v in dict(run_id=request['run_id'],input_sha256=request['input_sha256'],points=request['input_metadata']['points'],model_sha256=request['model_sha256'],vendor_revision='730cda1c730877cfedbe01bf87fb1cadb78a565d').items()):fail('output_invalid')
    return outputs


def execute(store,batch,case,plan,directory,check,closed,dependency=None):
    """Called while coordinator owns exactly one shared execution slot."""
    spec=plan['model_spec'];profile=case['profile_id'];binding=spec['runtimes'].get(profile)
    if binding is None:fail('runtime_not_designated')
    environment=preflight(binding,profile,directory,check,closed)
    with store.transaction() as db:
        store.event(db,batch,store._clock(db),'model_environment_ready',dict(case_id=case['case_id'],ready=True,observation=environment['observation'],policy=environment['policy']))
    candidate=next(x for x in plan['observation']['candidates'] if x['candidate_id']==case['candidate_id'])
    source_observation=plan['observation']['observations'][candidate['source_index']] if plan['observation']['kind']=='local_model_scopes' else plan['observation']
    source=safe_path(Path(source_observation['root']),candidate['relative'] or '.')
    manifest=manifest_table()[2][profile];started=time.monotonic()
    def hash_check():
        check()
        if time.monotonic()-started>spec['hash_seconds']:fail('hash_timeout')
    # Reserve full required bytes once before any weight read. Failed reads consume the budget.
    amount=sum(x['size'] for x in manifest['files'])
    with store.transaction() as db:
        old=db.execute('SELECT read_bytes FROM batches WHERE id=?',(batch,)).fetchone()[0]
        if old+amount>plan['limits']['read_bytes']+spec['hash_bytes']:fail('hash_budget_exceeded')
        db.execute('UPDATE batches SET read_bytes=read_bytes+? WHERE id=?',(amount,batch))
        store.event(db,batch,store._clock(db),'weight_hash_reserved',dict(case_id=case['case_id'],bytes=amount))
    def hash_progress(item):
        with store.transaction() as db:store.event(db,batch,store._clock(db),'weight_file_verified',dict(case_id=case['case_id'],path=item['path'],bytes=item['bytes'],sha256=item['sha256']))
    hashes=full_hash(source,manifest,hash_check,hash_progress)
    with store.transaction() as db:
        store.event(db,batch,store._clock(db),'model_artifact_verified',dict(case_id=case['case_id'],files=len(hashes),bytes=sum(x['bytes'] for x in hashes)))
    if profile=='tapir':
        _owned([binding['python'],'-I','-B',str(Path(__file__).with_name('validation_video_fixture.py')),str(directory/'input.mp4')],directory,check,closed,30,log_name='fixture.log')
    data,info,lineage=fresh_input(profile,batch,case['case_id'],directory,dependency)
    run_id=directory.name
    if profile.startswith('qwen3-tts-'):
        parameters={k:DEFAULTS[k] for k in ('language','speaker','batch_size','instruct','max_new_tokens','sampling')}|dict(seed=0)
        request=dict(run_id=run_id,model_id=profile,model_revision=manifest['revision'],model_path=str(source),text=data.decode('utf8'),parameters=parameters,input_sha256=info['sha256'])
        worker='tts_worker.py'
    else:
        kind=adapters.descriptor(profile)['task_type']
        parameters={'stt':dict(language='ko',task='transcribe',max_new_tokens=256,seed=0,do_sample=False),'llm':dict(max_new_tokens=64,max_input_tokens=256,seed=0,do_sample=False),'image':dict(seed=0,width=512,height=512,num_inference_steps=4,guidance_scale=4.0),'tracking':dict(points=info.get('points'),max_frames=32,resize=256)}[kind]
        request=dict(run_id=run_id,input_sha256=info['sha256'],model_path=str(source),parameters=parameters,input_metadata=info)
        if kind=='tracking':request['model_sha256']=manifest['files'][0]['sha256']
        worker=adapters.descriptor(profile)['worker']
    proof=dict(batch_id=batch,case_id=case['case_id'],run_id=run_id,plan_sha256=store.plan(plan['plan_id'])['sha'],profile_id=profile,
        revision=manifest['revision'],model_files=hashes,runtime=binding,environment=environment,lineage=lineage,code_sha256=plan['code_sha256'],model_test_performed=False)
    atomic_text(directory/'provenance.json',json.dumps(proof,ensure_ascii=False));atomic_text(directory/'request.json',json.dumps(request,ensure_ascii=False))
    environment=preflight(binding,profile,directory,check,closed,log_name='environment-dispatch.log')
    proof['environment_dispatch']=environment
    atomic_text(directory/'provenance.json',json.dumps(proof,ensure_ascii=False))
    check_spec(spec,plan['observation']);check()
    from .validation_store import control_code_sha
    if control_code_sha()!=plan['code_sha256']:fail('plan_code_or_catalog_stale')
    for item in hashes:
        path,pins=safe_path(source,item['path'],_with_identity=True)
        if pins!=item['parents'] or signature(path.stat())!=item['signature']:fail('source_changed')
    with store.transaction() as db:
        db.execute('UPDATE batches SET model_test=1 WHERE id=?',(batch,))
        store.event(db,batch,store._clock(db),'model_worker_dispatch',dict(case_id=case['case_id'],run_id=run_id))
    code=_owned([binding['python'],'-I','-B',str(Path(__file__).with_name(worker)),str(directory/'request.json')],directory,check,closed,spec['timeout_seconds'],log_name='worker.log',resource_gib=18 if profile=='qwen-image-2.1' else 12 if profile=='llama-3.1-8b-instruct' else None)
    result=metadata_json((directory/'result.json').read_bytes(),maximum=65536)
    if digest(directory/('input.wav' if profile=='whisper-large-v3-turbo' else 'input.mp4' if profile=='tapir' else 'input.txt'))!=info['sha256']:fail('input_changed')
    outputs=validate_outputs(profile,directory,request,result,code);check()
    proof.update(model_test_performed=True,outputs=outputs,status='succeeded',directory=str(directory),metrics=result['metrics'],
        request_sha256=digest(directory/'request.json'),result_sha256=digest(directory/'result.json'),
        ownership=metadata_json((directory/'worker.log.ownership.json').read_bytes()))
    atomic_text(directory/'receipt.json',json.dumps(proof,ensure_ascii=False,allow_nan=False))
    return proof
