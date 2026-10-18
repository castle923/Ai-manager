"""M12 bounded read-only observations. No model deserialization or network."""
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import time
from .validation_contracts import ContractError, fail, integer, document_sha, object_fields
from .validation_profiles import catalog, SPECS

POLICY = dict(version=1, max_entries=4096, max_depth=8, max_metadata_bytes=2097152,
              max_json_bytes=262144, max_seconds=15, model_code_execution=False)
DENIED = {'.git','.cache','cache','caches','.venv','node_modules','outputs','output','runs','logs','results','__pycache__'}
METADATA = {'config.json','model_index.json','preprocessor_config.json','processor_config.json',
            'tokenizer_config.json','generation_config.json','model.safetensors.index.json'}
WEIGHTS = {'.safetensors','.pt','.pth','.bin','.gguf','.onnx','.ckpt'}


def safe_path(root, relative='.', *, _with_identity=False):
    if not isinstance(root,(str,Path)) or any(ord(c)<32 for c in str(root)):
        fail('scope_path_invalid')
    root=Path(root)
    if not root.is_absolute() or '..' in root.parts:
        fail('scope_path_invalid')
    if type(relative) is not str or '\\' in relative or ':' in relative or relative.startswith('/'):
        fail('scope_path_invalid')
    parts=[] if relative=='.' else relative.split('/')
    if any(not p or p in ('.','..') or any(ord(c)<32 for c in p) for p in parts):
        fail('scope_path_invalid')
    target=root.joinpath(*parts)
    identities=[]
    try:
        for item in (*reversed(target.parents),target):
            info=item.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:
                fail('scope_reparse_rejected')
            identities.append((str(item),info.st_dev,info.st_ino,stat.S_IFMT(info.st_mode)))
    except (OSError,ValueError):
        fail('scope_unavailable')
    return (target,identities) if _with_identity else target


def signature(info):
    return [info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns]


def metadata_json(raw,*,maximum=262144,node_limit=8192):
    """Bounded non-executing JSON, including finite configuration floats."""
    if type(raw) is not bytes or len(raw)>maximum:fail('metadata_size_limit')
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:fail('metadata_duplicate_key')
            result[key]=value
        return result
    def bad(_):fail('metadata_number_invalid')
    try:value=json.loads(raw.decode('utf-8'),object_pairs_hook=pairs,parse_constant=bad)
    except ContractError:raise
    except (ValueError,UnicodeError,RecursionError):fail('metadata_json_invalid')
    counter=[0]
    def check(x,depth=0):
        counter[0]+=1
        if depth>24 or counter[0]>node_limit:fail('metadata_complexity_limit')
        if type(x) is float and not math.isfinite(x):fail('metadata_number_invalid')
        if type(x) is str and (len(x)>65536 or any(0xD800<=ord(c)<=0xDFFF for c in x)):fail('metadata_string_invalid')
        if type(x) is dict:
            for k,v in x.items():check(k,depth+1);check(v,depth+1)
        elif type(x) is list:
            for v in x:check(v,depth+1)
    check(value)
    if type(value) is not dict:fail('metadata_object_required')
    return value


def read_small(root,relative,remaining):
    path,pins=safe_path(root,relative,_with_identity=True)
    try:
        before=path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_size>min(remaining,POLICY['max_json_bytes']):fail('metadata_size_limit')
        with os.fdopen(os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)),'rb') as stream:
            opened=os.fstat(stream.fileno())
            if signature(opened)!=signature(before):fail('source_changed')
            if safe_path(root,relative,_with_identity=True)[1]!=pins:fail('source_parent_changed')
            raw=stream.read(min(remaining,POLICY['max_json_bytes'])+1)
            after=os.fstat(stream.fileno())
        current_path,current_pins=safe_path(root,relative,_with_identity=True)
        if current_pins!=pins:fail('source_parent_changed')
        current=current_path.lstat()
        if signature(before)!=signature(after) or signature(after)!=signature(current) or len(raw)!=before.st_size:fail('source_changed')
        return raw,signature(current)
    except ContractError:raise
    except (OSError,ValueError):fail('metadata_read_failed')


def manifest_table():
    profiles,fingerprint=catalog()
    manifests={}
    for name,expected,_,_,_ in SPECS:
        try:raw=(Path(__file__).parent/name).read_bytes()
        except OSError:fail('catalog_read_failed')
        if hashlib.sha256(raw).hexdigest()!=expected:fail('catalog_manifest_changed')
        data=json.loads(raw)
        manifests[data['model_id']]=data
    return profiles,fingerprint,manifests


def identify(files,parsed,manifests):
    """Exact small-config digest evidence selects a recipe, not weight integrity."""
    bypath={f['path']:f for f in files}
    matches=[];conflicts=[]
    for key,manifest in manifests.items():
        required={f['path']:f for f in manifest['files']}
        anchors=[p for p in ('config.json','model_index.json') if p in required and p in bypath]
        if not anchors:continue
        if all(bypath[p].get('sha256')==required[p]['sha256'] for p in anchors):
            matches.append(key)
            for p in anchors:
                declared=parsed.get(p,{}).get('_commit_hash')
                if declared is not None and declared!=manifest['revision']:conflicts.append(key)
    if conflicts:return dict(identity='conflicting',profile_id=None,revision=None,artifact='uninspected',not_observed=[],mismatched=[])
    if len(matches)>1:return dict(identity='ambiguous',profile_id=None,revision=None,artifact='uninspected',not_observed=[],mismatched=[])
    if not matches:
        status='unsupported' if any('model_type' in x or '_class_name' in x for x in parsed.values()) else 'unknown'
        hints=[dict(profile_id=k,expected_revision=m['revision'],strength='filename_and_size_only') for k,m in manifests.items()
               if any(p['path'] in bypath and bypath[p['path']]['bytes']==p['size'] for p in m['files'] if Path(p['path']).suffix in WEIGHTS)]
        return dict(identity=status,profile_id=None,revision=None,artifact='uninspected',not_observed=[],mismatched=[],weak_hints=hints)
    key=matches[0];manifest=manifests[key]
    missing=[];mismatched=[]
    for expected in manifest['files']:
        actual=bypath.get(expected['path'])
        if actual is None:missing.append(expected['path'])
        elif actual['bytes']!=expected['size'] or ('sha256' in actual and actual['sha256']!=expected['sha256']):mismatched.append(expected['path'])
    return dict(identity='supported_metadata',profile_id=key,revision=manifest['revision'],
                artifact='required_files_not_observed' if missing else 'hash_or_size_mismatch' if mismatched else 'metadata_matched_weights_unverified',
                not_observed=missing,mismatched=mismatched)


def observe_local(root,*,alias='local',clock=time.time,monotonic=time.monotonic,
                  depth_limit=8,json_limit=262144,read_limit=2097152,_manifests=None):
    if type(alias) is not str or not alias or len(alias)>64:fail('scope_alias_invalid')
    integer(POLICY['max_entries'],1)
    integer(depth_limit,0,8);integer(json_limit,1,262144);integer(read_limit,1,2097152)
    scope=dict(depth_limit=depth_limit,json_limit=json_limit,read_limit=read_limit)
    start=monotonic();root,root_pins=safe_path(root,_with_identity=True)
    if not root.is_dir():fail('scope_directory_required')
    root_info=root.stat()
    source_identity=observation_sha(dict(kind='local_physical_root',device=root_info.st_dev,inode=root_info.st_ino))
    profiles,cat,manifests=manifest_table()
    if _manifests is not None:manifests=_manifests  # Explicit synthetic test injection; CLI never exposes it.
    files=[];errors=[];excluded=[];read_bytes=0;count=0;folders=[];parsed_all={}
    def budget():
        if monotonic()-start>POLICY['max_seconds']:fail('scan_time_limit')
    queue=[('',0)]
    while queue:
        relative,depth=queue.pop(0)
        try:
            budget();directory,dir_pins=safe_path(root,relative or '.',_with_identity=True)
            if dir_pins[:len(root_pins)]!=root_pins:fail('source_parent_changed')
            before=directory.lstat()
            if not stat.S_ISDIR(before.st_mode):fail('source_changed')
            if safe_path(root,relative or '.',_with_identity=True)[1]!=dir_pins:fail('source_parent_changed')
            with os.scandir(directory) as it:
                entries=[]
                for entry in it:
                    count+=1
                    if count>POLICY['max_entries']:fail('scan_entry_limit')
                    budget();entries.append(entry.name)
            if signature(directory.lstat())!=signature(before) or safe_path(root,relative or '.',_with_identity=True)[1]!=dir_pins:fail('source_changed')
            folders.append(dict(path=relative,signature=signature(before)))
            for name in sorted(entries):
                child='/'.join(x for x in (relative,name) if x)
                if name.startswith('.') or name.casefold() in DENIED:
                    excluded.append(child);continue
                try:
                    if safe_path(root,_with_identity=True)[1]!=root_pins:fail('source_parent_changed')
                    path=safe_path(root,child);info=path.lstat()
                    if stat.S_ISDIR(info.st_mode):
                        if depth>=depth_limit:
                            if depth_limit==0:excluded.append(child);continue
                            fail('scan_depth_limit')
                        queue.append((child,depth+1));continue
                    if not stat.S_ISREG(info.st_mode):fail('nonregular_source')
                    item=dict(path=child,bytes=info.st_size,signature=signature(info))
                    if name in METADATA:
                        if info.st_size>json_limit:fail('metadata_size_limit')
                        raw,sig=read_small(root,child,read_limit-read_bytes)
                        read_bytes+=len(raw);budget()
                        item.update(sha256=hashlib.sha256(raw).hexdigest(),signature=sig)
                        parsed_all[child]=metadata_json(raw)
                    files.append(item)
                except ContractError as exc:errors.append(dict(path=child,reason=str(exc)))
        except (OSError,ValueError) as exc:
            errors.append(dict(path=relative,reason=str(exc) if isinstance(exc,ContractError) else 'scan_io_failed'))
            if isinstance(exc,ContractError) and str(exc) in ('scan_entry_limit','scan_time_limit'):break
    roots={str(Path(f['path']).parent).replace('\\','/') for f in files if Path(f['path']).name in ('config.json','model_index.json')}
    if not roots and any(Path(f['path']).suffix in WEIGHTS for f in files):roots={'.'}
    roots=sorted(roots,key=lambda x:(len(Path(x).parts),x));top=[]
    for r in roots:
        if not any(r==p or Path(r).is_relative_to(Path(p)) for p in top):top.append(r)
    candidates=[]
    for r in top:
        prefix='' if r=='.' else r+'/'
        subset=[dict(f,path=f['path'][len(prefix):]) for f in files if not prefix or f['path'].startswith(prefix)]
        parsed={p[len(prefix):]:v for p,v in parsed_all.items() if not prefix or p.startswith(prefix)}
        identity=identify(subset,parsed,manifests)
        candidates.append(dict(candidate_id=document_sha(dict(source_identity=source_identity,relative=r))[:32],relative=r,**identity))
    core=dict(schema_version=2,kind='local_readonly',alias=alias,root=str(root),source_identity=source_identity,policy=dict(POLICY),scope=scope,excluded=excluded,
              catalog_sha256=cat,files=files,folders=folders,errors=errors,candidates=candidates,
              complete=not errors,coverage_complete=not excluded and not errors,absence_means_deleted=False,
              read_bytes=read_bytes,model_test_performed=False)
    # Large observations use the same deterministic JSON policy, without M11's tiny-document cap.
    core['fingerprint']=observation_sha(core)
    return dict(core,observed_at_ms=int(clock()*1000))


def observation_sha(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()).hexdigest()


def reobserve(observation):
    if observation.get('kind')!='local_readonly':fail('stale_inventory_not_live_source')
    core={k:v for k,v in observation.items() if k not in ('fingerprint','observed_at_ms')}
    if observation_sha(core)!=observation['fingerprint']:fail('observation_tampered')
    current=observe_local(observation['root'],alias=observation['alias'],**observation['scope'])
    if not current['complete'] or current['fingerprint']!=observation['fingerprint']:fail('source_stale')
    return current


def observe_drive_inventory(value):
    """Explicit exported inventory only, never auth DB or a live Drive request."""
    try:metadata_json(json.dumps(value,allow_nan=False).encode(),maximum=4194304,node_limit=65536)
    except ContractError:raise
    except (ValueError,TypeError):fail('inventory_schema_invalid')
    object_fields(value,('schema_version','scope_alias','scan_id','observed_at','status','files'))
    if value['schema_version']!=1 or type(value['schema_version']) is not int:fail('inventory_schema_invalid')
    if type(value['files']) is not list or len(value['files'])>4096:fail('inventory_entry_limit')
    if value['status'] not in ('completed','partial','failed','cancelled'):fail('inventory_status_invalid')
    for item in value['files']:
        object_fields(item,('file_id','root_alias','path','kind','metadata'))
        if type(item['path']) is not str or item['path'].startswith('/') or '\\' in item['path'] or ':' in item['path'] or '..' in item['path'].split('/'):fail('inventory_path_invalid')
        if type(item['metadata']) is not dict:fail('inventory_metadata_invalid')
    return dict(schema_version=2,kind='drive_inventory_snapshot',scope_alias=value['scope_alias'],
        scan_id=value['scan_id'],observed_at=value['observed_at'],status=value['status'],
        files=value['files'],fingerprint=observation_sha(value),current_drive_verified=False,
        dispatchable=False,absence_means_deleted=False,model_test_performed=False)
