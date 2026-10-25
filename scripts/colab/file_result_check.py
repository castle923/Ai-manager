# Read-only bounded result inspection. Never rerun any live phase.
import json,math,os,pathlib,stat
CONTEXT_VALUE = "(globals().get('ROOT'), globals().get('PY'), globals().get('META'), globals().get('FRESH_META_TIME'), globals().get('env'), json.dumps(globals().get('FRESH_META'),sort_keys=True), tuple(sorted((name,item['sha256']) for name,item in globals().get('PAYLOADS',{}).items())))"
STAGES={'hash_begin','hash_complete','load_begin','load_complete','generate_begin','generate_end','done','cache_advisor_failed'}
STATUSES={'completed','stopped','single_Llama_LLM_INT8_GPU_smoke_pass'}
REASONS={'worker_exit_confirmation_timeout','cgroup_path_invalid','monitor_error','worker_exited','worker_exited_before_gate','OS_memory_floor','cgroup_memory_floor','RSS_cap','deadline_exceeded','log_monitor_error','log_size_cap','worker_identity_unavailable','worker_identity_changed','handshake_invalid','fresh_budget_insufficient','fresh_cgroup_budget_insufficient','handshake_deadline_exceeded','owned_cleanup_incomplete','log_reader_cleanup_incomplete','owned_descendant_survived','descendant_identity_changed','cgroup_membership_invalid','cgroup_mount_escape_rejected','cgroup_mount_unresolved','cgroup_mount_ambiguous','memory_measurement_failed','cgroup_access_path_invalid','cgroup_mount_device_mismatch','cgroup_memory_file_invalid'}
NUMBERS={'worker_returncode','final_worker_returncode','remaining_owned_count','elapsed_seconds','samples','peak_owned_RSS_bytes','minimum_available_RAM_bytes','minimum_cgroup_headroom_bytes','peak_cgroup_current_bytes','last_cgroup_max_bytes','peak_cgroup_file_bytes','baseline_RSS_bytes','incremental_budget_bytes','RSS_cap_bytes','stdout_saved_bytes','stderr_saved_bytes','generation_calls','input_tokens','new_tokens','loading_seconds','inference_seconds','GPU_peak_allocated_bytes','GPU_peak_reserved_bytes','cuda_parameter_bytes','quantized_linear_count','cpu_parameter_bytes','unique_GPU_parameter_and_quant_storage_bytes','parameter_count','bits','predicted_RSS_bytes','conservative_reference_increment_bytes','exit_confirmation_samples','exit_confirmation_seconds'}
BOOLEANS={'gate_opened','automatic_retry','sampled_guard_not_OS_memory_limit','eos_reached','length_cap_reached','disk_offload','CPU_offload','cleanup_measurement_error'}

def _whitelist(value):
    if type(value) is not dict:return {}
    result={k:v for k,v in value.items() if k in NUMBERS and type(v) in (int,float) and math.isfinite(v) and -65536<=v<=2**60}
    result.update({k:v for k,v in value.items() if k in BOOLEANS and type(v) is bool})
    if type(value.get('status')) is str and value['status'] in STATUSES:result['status']=value['status']
    for key,allowed in (('identity_observation',{'owned_zombie','process_absent','identity_changed','live_or_unknown','identity_unavailable'}),('exit_poll_path',{'main_poll','identity_repoll'})):
        if type(value.get(key)) is str and value[key] in allowed:result[key]=value[key]
    for key in ('reason','primary_reason'):
        if type(value.get(key)) is str and value[key] in REASONS:result[key]=value[key]
    if type(value.get('stage')) is str and value['stage'] in STAGES:result['stage']=value['stage']
    history=value.get('history')
    if type(history) is list:
        result['history']=[{'stage':item['stage'],'monotonic_seconds':item['monotonic_seconds']} for item in history[:16]
            if type(item) is dict and type(item.get('stage')) is str and item['stage'] in STAGES
            and type(item.get('monotonic_seconds')) in (int,float) and math.isfinite(item['monotonic_seconds']) and 0<=item['monotonic_seconds']<=2**60]
    for key in ('parameter_residency','quantization','memory_prediction'):
        if type(value.get(key)) is dict:result[key]=_whitelist(value[key])
    mapping=value.get('device_map')
    if type(mapping) is dict:
        values=list(mapping.values())
        result['device_counts']={'gpu':sum(type(v) is int and v==0 or type(v) is str and v in ('cuda','cuda:0') for v in values),
            'cpu':sum(type(v) is str and v=='cpu' for v in values),'disk':sum(type(v) is str and v=='disk' for v in values)}
    return result

def _root_valid(root):
    return (type(root) in (pathlib.PosixPath,pathlib.WindowsPath) and root.is_absolute()
        and root.parent==pathlib.Path('/content') and root.name.startswith('llama-t4-int8-')
        and '..' not in root.parts and not root.parent.is_symlink() and not root.is_symlink() and root.resolve()==root)

def _bounded_read(path,limit):
    if path.is_symlink() or path.parent.is_symlink() or path.parent.parent.is_symlink():raise ValueError()
    fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_BINARY',0))
    try:
        before=os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_size>limit:raise ValueError()
        chunks=[];remaining=before.st_size
        while remaining:
            part=os.read(fd,min(remaining,8192))
            if not part:raise ValueError()
            chunks.append(part);remaining-=len(part)
        if os.read(fd,1):raise ValueError()
        identity=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns)
        if path.is_symlink() or path.parent.is_symlink() or path.parent.parent.is_symlink() or identity(before)!=identity(os.fstat(fd)) or identity(before)!=identity(path.stat()):raise ValueError()
        return b''.join(chunks)
    finally:os.close(fd)

def inspect_file_results(namespace):
    report={'context_validated':False,'root_validated':False,'work_validated':False,'files':{},'finished_result_evidence':False,'guard_clean_completion_evidence':False}
    root=namespace.get('ROOT');context=namespace.get('RUNTIME_CONTEXT');download=namespace.get('DOWNLOAD')
    try:
        current=eval(CONTEXT_VALUE,{'globals':lambda:namespace,'json':json})
        report['context_validated']=(type(context) is tuple and context==current
            and namespace.get('DOWNLOAD_CONTEXT')==(context,namespace.get('load_reviewed'))
            and callable(namespace.get('load_reviewed')) and type(download) is dict
            and download.get('status')=='completed' and type(download.get('file_count')) is int and download['file_count']==10
            and type(download.get('total_bytes')) is int and download['total_bytes']==16069722669
            and download.get('full_weight_SHA_verified') is True and download.get('token_saved') is False
            and type(download.get('model_path')) is str and pathlib.Path(download['model_path'])==root/'model')
        if not report['context_validated']:return report
        report['root_validated']=bool(_root_valid(root))
        if not report['root_validated']:return report
        work=root/'inference-watchdog-fixed'
        report['work_validated']=(namespace.get('WORK')==work and not work.is_symlink() and work.resolve()==work and work.is_dir())
        if not report['work_validated']:return report
    except Exception:return report
    for name in ('phase.json','watchdog-summary.json','result.json','worker.stderr.log'):
        entry={'exists':False,'readable':False,'oversize':False};report['files'][name]=entry
        path=work/name;limit=16384 if name.endswith('.log') else 65536
        try:
            if path.is_symlink():entry['read_error']='symlink_rejected';continue
            info=path.stat();entry['exists']=True
            if not stat.S_ISREG(info.st_mode):entry['read_error']='not_regular';continue
            entry['bytes']=info.st_size;entry['oversize']=info.st_size>limit
            if entry['oversize']:entry['read_error']='size_limit';continue
            raw=_bounded_read(path,limit)
            if name.endswith('.json'):
                value=json.loads(raw)
                if type(value) is not dict:entry['read_error']='json_not_object';continue
                entry['data']=_whitelist(value)
            else:
                lower=raw.lower()
                entry['markers']={'warning':b'warning' in lower,'loading_shards':b'loading checkpoint shards' in lower,
                    'traceback':b'traceback (most recent call last)' in lower,
                    'oom':b'out of memory' in lower or b'outofmemoryerror' in lower}
            entry['readable']=True
        except Exception as error:
            kind=type(error).__name__
            entry['read_error']=kind if kind in ('FileNotFoundError','PermissionError','OSError','JSONDecodeError','UnicodeDecodeError','ValueError','TypeError','RecursionError') else 'OtherException'
    result=report['files'].get('result.json',{}).get('data',{})
    guard=report['files'].get('watchdog-summary.json',{}).get('data',{})
    phase=report['files'].get('phase.json',{}).get('data',{})
    report['phase_done_evidence']=phase.get('stage')=='done' or any(item.get('stage')=='done' for item in phase.get('history',[]))
    report['finished_result_evidence']=(result.get('status')=='single_Llama_LLM_INT8_GPU_smoke_pass' and result.get('generation_calls')==1 and type(result.get('new_tokens')) is int and 0<result['new_tokens']<=32)
    report['guard_clean_completion_evidence']=(guard.get('status')=='completed' and guard.get('gate_opened') is True and guard.get('worker_returncode')==0 and guard.get('remaining_owned_count')==0)
    return report

def print_file_result_check(namespace):
    if 'RUNTIME_CONTEXT' not in namespace and 'DOWNLOAD_CONTEXT' not in namespace:
        print('__RESULT_CHECK_SKIPPED__'+json.dumps({'status':'not_ready','reason':'live_context_absent'},sort_keys=True))
        return
    print('__FILE_RESULT_CHECK__'+json.dumps(inspect_file_results(namespace),sort_keys=True,allow_nan=False))
