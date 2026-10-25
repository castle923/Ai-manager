"""One separately approved offline Llama LLM.int8 smoke. Fresh measured handshake must precede model loading."""
import argparse,threading,gc,hashlib,importlib.metadata as im,json,os,pathlib,sys,time,traceback,struct,types,platform,importlib.util,stat
HERE=pathlib.Path(__file__).resolve().parent
contract_path=HERE/'colab_contract.py'
if not contract_path.is_file():contract_path=HERE.parents[1]/'src/ai_manager/colab_contract.py'
cspec=importlib.util.spec_from_file_location("handoff_contract",contract_path)
contract=importlib.util.module_from_spec(cspec);cspec.loader.exec_module(contract)
META_SHA='895838740157e1f934cf704dd0b712de3493be4dd23d6bd33e57b3ba5949e8ad'
MANIFEST_SHA='a8fcf721121d9704daea0b45189868cdc479b18e6755df07d984e8637007318d'
GiB=1024**3
CHUNK=1024**2
attempts=[]
def audit(event,args):
    if event in ('socket.connect','socket.getaddrinfo','socket.sendto','socket.bind'):
        local=(event=='socket.bind' and args[1]==('::1',0) and any(f.name=='_has_ipv6' and f.filename.endswith('/urllib3/util/connection.py') for f in traceback.extract_stack(limit=8)))
        attempts.append({'event':event,'blocked_local_capability_probe':local});raise RuntimeError('offline_network_denied')

def sha(path):
    h=hashlib.sha256()
    with pathlib.Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()
def write_new(path,value):
    target=pathlib.Path(path);pending=target.with_name('.'+target.name+'.pending')
    assert not target.exists() and not target.is_symlink()
    with pending.open('x',encoding='utf-8') as f:json.dump(value,f,indent=2);f.flush();os.fsync(f.fileno())
    os.link(pending,target);pending.unlink()

class InputTokenLimit(ValueError):
    pass

def prepare_input(tokenizer,text):
    ids=tokenizer.apply_chat_template([{'role':'user','content':text}],add_generation_prompt=True,return_tensors='pt')
    if ids.ndim!=2 or ids.shape[0]!=1 or not 0<ids.shape[1]<=64:raise InputTokenLimit('input_token_limit')
    return ids

def generate_once(model,ids,mask,eos_set):
    return model.generate(input_ids=ids,attention_mask=mask,max_new_tokens=32,do_sample=False,use_cache=True,pad_token_id=min(eos_set),return_dict_in_generate=True,output_scores=True)

def termination(count,last,eos_set):
    if not 0<count<=32 or last not in eos_set and count!=32:raise ValueError('output_invalid')
    reached=last in eos_set
    return reached,not reached and count==32

def validate_app_context(context,request,pins,root,work):
    expected=dict(request_sha256=request['request_sha256'],source_sha256=pins,model_root=str(root),work=str(work))
    if context!=expected or work.name!=request['request_id'] or (work/'app-request.once').read_text()!=request['request_sha256']:
        raise ValueError('context_mismatch')
def main():
    a=argparse.ArgumentParser();a.add_argument('--model',required=True);a.add_argument('--manifest',required=True);a.add_argument('--request',required=True);a.add_argument('--context',required=True);a.add_argument('--output',required=True);a.add_argument('--watchdog-handshake',required=True);a.add_argument('--watchdog-gate',required=True);args=a.parse_args()
    phase_lock=threading.Lock();phase_history=[];phase_path=pathlib.Path(args.output).parent/'phase.json'
    def write_phase(stage):
        assert stage in ('hash_begin','hash_complete','load_begin','load_complete','generate_begin','generate_end','done','cache_advisor_failed')
        with phase_lock:
            phase_history.append({'stage':stage,'monotonic_seconds':time.monotonic()})
            pending=phase_path.with_name('.phase-'+str(len(phase_history))+'.pending')
            with pending.open('x',encoding='utf-8') as f:json.dump({'stage':stage,'history':phase_history},f);f.flush();os.fsync(f.fileno())
            os.replace(pending,phase_path)
    write_phase('hash_begin')
    assert os.sysconf('SC_PAGE_SIZE')==4096
    assert os.environ.get('HF_ENABLE_PARALLEL_LOADING')=='false' and os.environ.get('HF_PARALLEL_LOADING_WORKERS')=='1'
    sys.addaudithook(audit)
    pins=json.loads((HERE/'colab_source_pins.json').read_bytes())
    for key,name in [('contract','colab_contract.py'),('worker','llama_handoff_worker.py'),('guard','llama_watchdog.py')]:assert sha(HERE/name)==pins[key],'source_mismatch'
    assert sha(args.manifest)==MANIFEST_SHA
    assert dict(python=platform.python_version(),**{n:im.version(n) for n in contract.RUNTIME if n!='python'})==contract.RUNTIME,'runtime_mismatch'
    request=contract.validate_request(contract.parse_document(pathlib.Path(args.request).read_bytes(),'request'),pins)
    context=json.loads(pathlib.Path(args.context).read_bytes())
    root=pathlib.Path(args.model)
    work=pathlib.Path(args.output).parent
    validate_app_context(context,request,pins,root,work)
    manifest=json.loads(pathlib.Path(args.manifest).read_bytes())
    assert len(manifest['files'])==10 and sum(x['size'] for x in manifest['files'])==16_069_722_669
    cache_guard=types.SimpleNamespace(_checked_shards=_checked_shards,_open=_open,_finish=_finish,verify_shard=verify_shard)
    for item in manifest['files']:
        p=root/item['path'];assert p.is_file() and not p.is_symlink() and p.stat().st_size==item['size']
        digest=cache_guard.verify_shard(p,root,args.manifest) if item['path'].endswith('.safetensors') else sha(p)
        assert digest==item['sha256'],'model_file_verification_failed'
    tensors={}
    for item in manifest['files']:
        if not item['path'].endswith('.safetensors'):continue
        with (root/item['path']).open('rb') as f:
            size=struct.unpack('<Q',f.read(8))[0];assert 0<size<2*1024**2
            header=json.loads(f.read(size))
        for name,record in header.items():
            if name=='__metadata__':continue
            assert record['dtype'] in ('F16','BF16') and name not in tensors
            count=1
            for dimension in record['shape']:count*=dimension
            tensors[name]=dict(shape=record['shape'],fp16_bytes=count*2)
    assert len(tensors)==291 and sum(x['fp16_bytes'] for x in tensors.values())==16_060_522_496
    m=dict(config=json.loads((root/'config.json').read_bytes()),tensors=tensors)
    write_phase('hash_complete')
    cache_hints=[]
    for item in manifest['files']:
        if not item['path'].endswith('.safetensors'):continue
        path=root/item['path'];before=path.stat()
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
        try:os.posix_fadvise(fd,0,0,os.POSIX_FADV_DONTNEED)
        finally:os.close(fd)
        after=path.stat();assert (before.st_size,before.st_mtime_ns)==(after.st_size,after.st_mtime_ns)
        cache_hints.append({'path':item['path'],'hint':'POSIX_FADV_DONTNEED','effect_verified':False})
    assert len(cache_hints)==4
    import psutil,torch,transformers,accelerate
    from transformers import LlamaConfig,LlamaForCausalLM,AutoTokenizer,BitsAndBytesConfig
    import bitsandbytes as bnb
    assert im.version("bitsandbytes")=="0.50.2"
    from accelerate import init_empty_weights,infer_auto_device_map
    assert sys.version_info[:2]==(3,12) and torch.__version__=='2.11.0+cu128'
    assert transformers.__version__=='4.57.3' and accelerate.__version__=='1.12.0'
    assert torch.cuda.device_count()==1 and torch.cuda.get_device_name(0)=='Tesla T4'
    x=torch.tensor([[1.,2.],[3.,4.]],device='cuda',dtype=torch.float16);y=x@x;torch.cuda.synchronize()
    assert torch.equal(y.cpu(),torch.tensor([[7.,10.],[15.,22.]],dtype=torch.float16));del x,y;torch.cuda.empty_cache()
    free,total=torch.cuda.mem_get_info();budget=min(12*GiB,free-int(2.5*GiB));assert budget>=11*GiB
    cfg=LlamaConfig(**m['config']);cfg._attn_implementation='sdpa'
    previous=torch.get_default_dtype();torch.set_default_dtype(torch.float16)
    try:
        with init_empty_weights(include_buffers=True):meta=LlamaForCausalLM(cfg)
    finally:torch.set_default_dtype(previous)
    params=dict(meta.named_parameters());assert set(params)==set(m['tensors'])
    for n,p in params.items():assert p.device.type=='meta' and list(p.shape)==m['tensors'][n]['shape'] and p.numel()*p.element_size()==m['tensors'][n]['fp16_bytes']
    mapping={'':0}
    linear_names=[n for n,module in meta.named_modules() if isinstance(module,torch.nn.Linear) and n!='lm_head']
    assert len(linear_names)==224
    int8_weight_bytes=sum(params[n+'.weight'].numel() for n in linear_names)
    scale_estimate_bytes=sum(params[n+'.weight'].shape[0]*4 for n in linear_names)
    weight_total=16_060_522_496;quant_state_estimate=weight_total-int8_weight_bytes+scale_estimate_bytes
    largest=max(t['fp16_bytes'] for t in m['tensors'].values())
    assert quant_state_estimate==9_086_705_664
    assert quant_state_estimate+2*largest+int(1.5*GiB)<=free,'INT8_GPU_conservative_budget_insufficient'
    weights={'cpu':0,'gpu_estimated':quant_state_estimate}
    del params,meta;gc.collect();torch.cuda.empty_cache()
    incremental=5_570_220_032;process=psutil.Process();baseline=process.memory_info().rss
    handshake=pathlib.Path(args.watchdog_handshake);gate=pathlib.Path(args.watchdog_gate)
    write_new(handshake,{'pid':os.getpid(),'create_time':process.create_time(),'baseline_rss_bytes':baseline,'incremental_budget_bytes':incremental,'device_map':mapping,'assigned_weight_bytes':weights,'GPU_free_bytes':free,'GPU_budget_bytes':budget,'maximum_tensor_bytes':largest,'metadata_sha256':request['request_sha256'],'conservative_reference_increment_bytes':6_587_346_784,'cache_hints':cache_hints})
    until=time.monotonic()+120
    while not gate.exists():
        assert time.monotonic()<until,'watchdog_gate_timeout';time.sleep(.05)
    permission=json.loads(gate.read_text());assert permission['pid']==os.getpid() and abs(permission['create_time']-process.create_time())<.001
    assert baseline+incremental<permission['RSS_cap_bytes'] and permission['OS_floor_bytes']>=2*GiB
    assert len(attempts)<=1 and all(x['blocked_local_capability_probe'] for x in attempts),'unexpected_network_attempt'
    tokenizer=AutoTokenizer.from_pretrained(str(root),local_files_only=True,trust_remote_code=False)
    try:ids=prepare_input(tokenizer,request['input']['text'])
    except InputTokenLimit:
        write_new(args.output,{'reason':'input_token_limit'});return
    torch.manual_seed(0);torch.cuda.manual_seed_all(0);torch.cuda.reset_peak_memory_stats()
    started=time.monotonic()
    quant=BitsAndBytesConfig(load_in_8bit=True,llm_int8_has_fp16_weight=False,llm_int8_enable_fp32_cpu_offload=False,llm_int8_skip_modules=['lm_head'])
    advisor=ShardCacheAdvisor(root,args.manifest,cache_guard,write_phase,interval=.2)
    write_phase('load_begin');advisor.start()
    try:
        model=LlamaForCausalLM.from_pretrained(str(root),local_files_only=True,trust_remote_code=False,use_safetensors=True,torch_dtype=torch.float16,attn_implementation='sdpa',device_map=mapping,quantization_config=quant)
        torch.cuda.synchronize()
    finally:advisor.stop()
    write_phase('load_complete')
    model.eval();assert model.hf_device_map==mapping and all(v!='disk' for v in model.hf_device_map.values())
    quantized=[(n,module) for n,module in model.named_modules() if isinstance(module,bnb.nn.Linear8bitLt)]
    assert len(quantized)==224 and set(n for n,_ in quantized)==set(linear_names)
    residency={'cuda_parameter_bytes':0,'quantized_linear_count':len(quantized),'cpu_parameter_bytes':0,'disk_offload':False}
    actual_params=dict(model.named_parameters());assert set(actual_params)==set(m['tensors']) and len(actual_params)==291
    storages={}
    def count_storage(tensor):
        assert tensor.device.type=='cuda'
        storage=tensor.untyped_storage();key=(str(tensor.device),storage.data_ptr())
        storages[key]=storage.nbytes()
    for n,param in actual_params.items():
        assert list(param.shape)==m['tensors'][n]['shape']
        assert param.device.type=='cuda','all_parameters_must_be_GPU_resident'
        residency['cuda_parameter_bytes']+=param.numel()*param.element_size()
        count_storage(param)
    for n,module in quantized:
        assert isinstance(module.weight,bnb.nn.Int8Params) and not module.weight.has_fp16_weights
        assert module.weight.dtype==torch.int8 and module.weight.device.type=='cuda'
        cb=module.weight.CB if module.weight.CB is not None else module.state.CB
        if cb is None:cb=module.weight.data
        scale=module.weight.SCB if module.weight.SCB is not None else module.state.SCB
        assert cb.device.type=='cuda' and cb.dtype==torch.int8 and list(cb.shape)==m['tensors'][n+'.weight']['shape']
        assert scale is not None and scale.device.type=='cuda' and scale.dtype==torch.float32 and list(scale.shape)==[module.out_features] and torch.isfinite(scale).all()
        count_storage(cb);count_storage(scale)
    residency['unique_GPU_parameter_and_quant_storage_bytes']=sum(storages.values());residency['parameter_count']=len(actual_params)
    assert model.get_input_embeddings().weight.dtype==torch.float16 and model.lm_head.weight.dtype==torch.float16
    assert all(module.weight.dtype==torch.float16 for n,module in model.named_modules() if 'norm' in n and hasattr(module,'weight'))
    generation_free,generation_total=torch.cuda.mem_get_info()
    assert generation_free>=int(1.5*GiB),'INT8_generation_VRAM_margin_insufficient'
    residency['generation_fresh_GPU_free_bytes']=generation_free
    ids=ids.to(model.get_input_embeddings().weight.device);mask=torch.ones_like(ids)
    eos=model.generation_config.eos_token_id;eos_set={eos} if isinstance(eos,int) else set(eos);assert eos_set
    loading=time.monotonic()-started;generation_started=time.monotonic()
    # Exactly one generation call. No retry/fallback/model patch; approved LLM.int8 only.
    write_phase('generate_begin')
    with torch.inference_mode():out=generate_once(model,ids,mask,eos_set)
    torch.cuda.synchronize();seconds=time.monotonic()-generation_started
    write_phase('generate_end')
    new=out.sequences[0,ids.shape[1]:].detach().cpu();assert 0<new.numel()<=32
    assert all(torch.isfinite(s).all().item() for s in out.scores),'nonfinite_generation_scores'
    decoded=tokenizer.decode(new,skip_special_tokens=True);assert decoded.strip()
    assert len(attempts)<=1 and all(x['blocked_local_capability_probe'] for x in attempts),'unexpected_network_attempt'
    eos_reached,cap=termination(new.numel(),int(new[-1]),eos_set)
    result={'response':{'text':decoded,'input_tokens':int(ids.shape[1]),'generated_tokens':int(new.numel()),'eos_reached':eos_reached,'length_cap_reached':cap},'engine':{'generation_calls':1,'quantized_linear_count':len(quantized),'gpu_parameter_tensor_count':len(actual_params),'cpu_offload':False,'disk_offload':False,'model_sha_verified':True,'runtime_verified':True}}
    write_new(args.output,result);write_phase('done')
def _identity(s):return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns)
def _open(path,size):
    path=pathlib.Path(path);assert not path.is_symlink()
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        before=os.fstat(fd)
        assert stat.S_ISREG(before.st_mode) and before.st_size==size and _identity(path.stat())==_identity(before)
        return fd,before
    except BaseException:os.close(fd);raise
def _finish(fd,path,before):
    assert _identity(os.fstat(fd))==_identity(before)==_identity(pathlib.Path(path).stat())
    assert not pathlib.Path(path).is_symlink()
def _checked_shards(root,manifest):
    root=pathlib.Path(root);manifest=pathlib.Path(manifest)
    assert root.is_absolute() and root.name=='model' and root.parent.parent==pathlib.Path('/content') and root.parent.name.startswith('llama-t4-int8-')
    assert not root.is_symlink() and root.resolve()==root and root.is_dir()
    raw=manifest.read_bytes();assert hashlib.sha256(raw).hexdigest()==MANIFEST_SHA
    items=[x for x in json.loads(raw)['files'] if x['path'].endswith('.safetensors')]
    assert len(items)==4 and {x['path'] for x in items}=={f'model-{i:05d}-of-00004.safetensors' for i in range(1,5)}
    return {str(root/x['path']):x for x in items}
def hint_exact_downloaded_shards(root,manifest):
    """No body read: advise exactly the four new VM shards, then caller samples."""
    records=[]
    for path,item in _checked_shards(root,manifest).items():
        fd,before=_open(path,item['size'])
        try:
            os.posix_fadvise(fd,0,0,os.POSIX_FADV_DONTNEED);_finish(fd,path,before)
        finally:os.close(fd)
        records.append({'path':item['path'],'size':item['size'],'hint':'DONTNEED','effect_verified':False})
    return records
def _verify_readonly(path,size,expected_sha,advise=None):
    """Private synthetic-testable core; bounded body reads, SHA unchanged."""
    if advise is None:advise=os.posix_fadvise
    fd,before=_open(path,size);h=hashlib.sha256();offset=0
    try:
        while offset<size:
            data=os.read(fd,min(CHUNK,size-offset));assert data,'short_read'
            h.update(data);end=offset+len(data)
            # Evict complete pages already hashed on the very same descriptor.
            first=(offset+4095)//4096*4096;last=end//4096*4096
            if last>first:advise(fd,first,last-first,os.POSIX_FADV_DONTNEED)
            offset=end
        assert os.read(fd,1)==b'' and offset==size,'size_changed'
        digest=h.hexdigest();assert digest==expected_sha,'SHA_mismatch'
        advise(fd,0,0,os.POSIX_FADV_DONTNEED);_finish(fd,path,before)
        return digest
    finally:os.close(fd)
def verify_shard(path,root,manifest):
    path=pathlib.Path(path);items=_checked_shards(root,manifest);assert str(path) in items,'shard_scope_rejected'
    item=items[str(path)];return _verify_readonly(path,item['size'],item['sha256'])

class ShardCacheAdvisor:
    def __init__(self,root,manifest,checked_helper,on_failure,interval=.2):
        assert .1<=interval<=.2
        self.helper=checked_helper;self.on_failure=on_failure;self.interval=interval
        self.entries=[];self.event=threading.Event();self.thread=None;self.closed=False
        try:
            for path,item in self.helper._checked_shards(root,manifest).items():
                fd,before=self.helper._open(path,item['size']);self.entries.append((fd,path,before))
            assert len(self.entries)==4
        except BaseException:
            for fd,_,_ in self.entries:os.close(fd)
            raise
    def _fatal(self):
        try:self.on_failure('cache_advisor_failed')
        except BaseException:pass
        try:os.write(2,b'cache_advisor_failed\n')
        finally:os._exit(72)
    def _hint_once(self):
        for fd,path,before in self.entries:
            self.helper._finish(fd,path,before)
            os.posix_fadvise(fd,0,0,os.POSIX_FADV_DONTNEED)
            self.helper._finish(fd,path,before)
    def _run(self):
        try:
            while not self.event.is_set():
                self._hint_once()
                if self.event.wait(self.interval):break
        except BaseException:self._fatal()
    def start(self):
        assert self.thread is None and not self.closed
        self.thread=threading.Thread(target=self._run,name='owned-shard-cache-advisor',daemon=True)
        self.thread.start()
    def stop(self):
        if self.closed:return
        self.event.set()
        if self.thread is not None:
            self.thread.join(timeout=2)
            if self.thread.is_alive():self._fatal();return
        try:
            for fd,path,before in self.entries:self.helper._finish(fd,path,before)
        except BaseException:self._fatal();return
        for fd,_,_ in self.entries:os.close(fd)
        self.closed=True

if __name__=='__main__':main()
