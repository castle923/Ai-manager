"""M12 live read-only Drive intake with explicit existing allowlist roots."""
import hashlib
import json
from pathlib import PurePosixPath
import time
from .drive import Drive,FOLDER,SHORTCUT,DriveError,valid_id
from .validation_contracts import fail,integer
from .validation_intake import METADATA,DENIED,WEIGHTS,metadata_json,manifest_table,identify,observation_sha


class BoundedSession:
    """Wrap the existing Drive client transport; no token/body/URL is logged."""
    def __init__(self,session,*,seconds=60,network_limit=2097152):
        self.session=session;self.deadline=time.monotonic()+seconds;self.limit=network_limit;self.bytes=0;self.calls=0

    def get(self,url,**kwargs):
        import requests
        remaining=self.deadline-time.monotonic()
        if remaining<=0 or self.calls>=64:raise DriveError('intake_request_budget_exceeded')
        if not url.startswith('https://www.googleapis.com/drive/v3/files'):raise DriveError('intake_endpoint_rejected')
        self.calls+=1
        params=dict(kwargs.get('params',{}))
        if 'pageSize' in params:params['pageSize']=100
        kwargs.update(params=params,timeout=(min(3,remaining),min(5,remaining)),stream=True,allow_redirects=False)
        response=self.session.get(url,**kwargs)
        parent=self
        class Response:
            status_code=response.status_code
            def __enter__(self):return self
            def __exit__(self,*_):response.close()
            def iter_content(self,chunk_size=16384):
                for chunk in response.iter_content(chunk_size=min(chunk_size,16384)):
                    parent.bytes+=len(chunk)
                    if parent.bytes>parent.limit or time.monotonic()>=parent.deadline:
                        response.close();raise DriveError('intake_network_budget_exceeded')
                    yield chunk
            def json(self):
                data=bytearray()
                try:
                    for chunk in self.iter_content():
                        data.extend(chunk)
                        if len(data)>262144:raise DriveError('intake_response_size_limit')
                    return metadata_json(bytes(data))
                finally:response.close()
        return Response()


class LiveDriveIntake:
    def __init__(self,drive,settings,account,root_id,*,depth_limit=2,json_limit=32768,read_limit=131072):
        if account not in ('A','B') or not valid_id(root_id):fail('drive_scope_invalid')
        if not any(r['account']==account and r['id']==root_id for r in settings['allowlist']):fail('drive_root_not_allowlisted')
        integer(depth_limit,0,8);integer(json_limit,1,32768);integer(read_limit,1,2097152)
        self.drive=drive;self.account=account;self.root=root_id
        self.scope=dict(depth_limit=depth_limit,json_limit=json_limit,read_limit=read_limit)
        self.settings_sha=observation_sha(dict(accounts=settings['accounts'],allowlist=settings['allowlist'],sources=settings.get('sources',[])))

    def observe(self):
        from .validation_contracts import ContractError
        start=time.monotonic();files=[];folders=[];errors=[];excluded=[];parsed={};used=0;entries=0;pages=0
        path_ids={};id_metadata={}
        _,cat,manifests=manifest_table()
        try:
            root=self.drive.metadata(self.root)
            if root.get('id')!=self.root or root.get('mimeType')!=FOLDER or root.get('trashed'):fail('drive_root_not_folder')
            folders.append(dict(path='',metadata=root))
            queue=[(self.root,'',0)];visited={self.root}
            while queue:
                parent,relative,depth=queue.pop(0);token=None;seen_tokens=set()
                while True:
                    if time.monotonic()-start>60:fail('drive_time_limit')
                    pages+=1
                    if pages>32:fail('drive_page_limit')
                    result=self.drive.children(parent,token)
                    if result.get('incompleteSearch') is True:fail('drive_partial_search')
                    children=result.get('files')
                    if type(children) is not list or len(children)>1000:fail('drive_children_invalid')
                    for metadata in children:
                        entries+=1
                        if entries>4096:fail('drive_entry_limit')
                        if type(metadata) is not dict:fail('drive_metadata_invalid')
                        name=metadata.get('name');fid=metadata.get('id')
                        if type(name) is not str or not name or '/' in name or '\\' in name or ':' in name or any(ord(c)<32 or 0xD800<=ord(c)<=0xDFFF for c in name) or name in ('.','..') or not valid_id(fid):fail('drive_metadata_invalid')
                        if metadata.get('trashed') or parent not in metadata.get('parents',[]):fail('drive_scope_parent_mismatch')
                        path='/'.join(x for x in (relative,name) if x)
                        if name.startswith('.') or name.casefold() in DENIED:excluded.append(path);continue
                        path_key=(parent,name.casefold())
                        if path_key in path_ids and path_ids[path_key]!=fid:fail('drive_ambiguous_name')
                        if fid in id_metadata:
                            fail('drive_duplicate_observation' if id_metadata[fid]==metadata else 'drive_id_conflict')
                        path_ids[path_key]=fid;id_metadata[fid]=metadata
                        kind=metadata.get('mimeType')
                        if kind==SHORTCUT:errors.append(dict(path=path,reason='drive_shortcut_rejected'));continue
                        if fid in visited:fail('drive_duplicate_or_cycle')
                        visited.add(fid)
                        if kind==FOLDER:
                            folders.append(dict(path=path,metadata=metadata))
                            if depth<self.scope['depth_limit']:queue.append((fid,path,depth+1))
                            else:excluded.append(path)
                            continue
                        size=metadata.get('size')
                        if type(size) is str and size.isdigit():size=int(size)
                        integer(size,0,2**53-1)
                        item=dict(path=path,bytes=size,metadata=metadata)
                        if name in METADATA:
                            if size>self.scope['json_limit'] or used+size>self.scope['read_limit']:fail('drive_metadata_read_limit')
                            raw=bytearray()
                            for chunk in self.drive.content(fid,size=size):
                                raw.extend(chunk)
                                if len(raw)>size or len(raw)>self.scope['json_limit']:fail('drive_content_size_mismatch')
                            if len(raw)!=size:fail('drive_content_size_mismatch')
                            fresh=self.drive.metadata(fid)
                            if fresh!=metadata:fail('drive_source_changed')
                            used+=len(raw);item['sha256']=hashlib.sha256(raw).hexdigest();parsed[path]=metadata_json(bytes(raw))
                        files.append(item)
                    token=result.get('nextPageToken')
                    if token is None:break
                    if type(token) is not str or not token or len(token)>2048 or token in seen_tokens:fail('drive_page_token_invalid')
                    seen_tokens.add(token)
        except (DriveError,ContractError) as exc:
            errors.append(dict(path='',reason=str(exc)))
        candidates=[]
        roots=sorted({str(PurePosixPath(f['path']).parent) for f in files if PurePosixPath(f['path']).name in ('config.json','model_index.json')},key=lambda x:(len(PurePosixPath(x).parts),x))
        if not roots:roots=sorted({str(PurePosixPath(f['path']).parent) for f in files if PurePosixPath(f['path']).suffix in WEIGHTS})
        selected=[]
        for root in roots:
            if not any(PurePosixPath(root).is_relative_to(PurePosixPath(p)) for p in selected):selected.append(root)
        for root in selected:
            prefix='' if root=='.' else root+'/'
            subset=[dict(f,path=f['path'][len(prefix):]) for f in files if not prefix or f['path'].startswith(prefix)]
            values={p[len(prefix):]:v for p,v in parsed.items() if not prefix or p.startswith(prefix)}
            candidates.append(dict(candidate_id=observation_sha(dict(account=self.account,root_id=self.root,relative=root))[:32],relative=root,**identify(subset,values,manifests)))
        if any(e['reason'] in ('drive_ambiguous_name','drive_id_conflict') for e in errors):
            for candidate in candidates:candidate.update(identity='ambiguous',profile_id=None,revision=None,artifact='uninspected')
        files.sort(key=lambda x:x['path']);folders.sort(key=lambda x:x['path']);excluded.sort()
        core=dict(schema_version=2,kind='drive_live_readonly',account=self.account,root_id=self.root,
            source_identity=observation_sha(dict(account=self.account,root_id=self.root)),
            settings_sha256=self.settings_sha,scope=self.scope,catalog_sha256=cat,files=files,folders=folders,
            candidates=candidates,complete=not errors,errors=errors,excluded=excluded,read_bytes=used,
            pages=pages,current_drive_verified=not errors,coverage_complete=not errors and not excluded,
            network_bytes=getattr(getattr(self.drive,'session',None),'bytes',0),
            network_requests=getattr(getattr(self.drive,'session',None),'calls',0),
            absence_means_deleted=False,model_test_performed=False)
        evidence={k:v for k,v in core.items() if k not in ('network_bytes','network_requests')}
        return dict(core,fingerprint=observation_sha(evidence),observed_at_ms=int(time.time()*1000))

    def reobserve(self,previous):
        core={k:v for k,v in previous.items() if k not in ('fingerprint','observed_at_ms','network_bytes','network_requests')}
        if observation_sha(core)!=previous.get('fingerprint'):fail('observation_tampered')
        if previous.get('root_id')!=self.root or previous.get('account')!=self.account or previous.get('settings_sha256')!=self.settings_sha or previous.get('scope')!=self.scope:fail('drive_scope_mismatch')
        current=self.observe()
        if not current['complete'] or current['fingerprint']!=previous['fingerprint']:fail('source_stale')
        return current


def authenticated_provider(auth_home,account,root_id,**scope):
    import requests
    from .config import SettingsStore
    from .auth import AuthManager
    from .security import SecretStore
    # Caller must explicitly choose a newly initialized M12 authentication home.
    settings=SettingsStore(auth_home).load()
    auth=AuthManager(settings,SecretStore(auth_home/'credentials'))
    auth.access(account)  # Fails before scanning if no user-authorized credential exists.
    session=BoundedSession(requests.Session())
    drive=Drive(lambda force_refresh=False:auth.access(account,force_refresh=force_refresh),session=session)
    return LiveDriveIntake(drive,settings,account,root_id,**scope)
