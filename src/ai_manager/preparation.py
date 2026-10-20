"""Single approved model preparation. Private immutable run directories, no inference."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
import uuid
import requests
from datetime import datetime, timezone

from .drive import Drive, DriveError, Cancelled, FOLDER
from .inventory import Inventory
from .models import DEFAULT_MODEL, load_manifest, model_ids, segment

MODEL_SEGMENT = 'Qwen3-TTS-12Hz-0.6B-CustomVoice'
ACTIVE = threading.Lock()

def now():
    return datetime.now(timezone.utc).isoformat()

def atomic_text(path, encoded):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.parent/(uuid.uuid4().hex+'.tmp')
    temporary.write_text(encoded,encoding='utf8')
    for attempt in range(40):
        try:
            os.replace(temporary,path)
            return
        except PermissionError:
            if attempt==39:raise
            time.sleep(0.05)

def manifest(model_id=DEFAULT_MODEL):
    return load_manifest(model_id)

def safe_relative(value):
    if not isinstance(value,str) or not value or '\\' in value or ':' in value or value.startswith('/'):
        raise ValueError('unsafe_path')
    parts=value.split('/')
    for part in parts:
        if part in ('','.','..') or part.endswith((' ','.')) or re.search(r'[<>"|?*\x00-\x1f]',part) or re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?',part):
            raise ValueError('unsafe_path')
    return Path(*parts)

def supported(item):
    return item.get('account')=='B' and any(segment(mid) in item.get('path','').split('/') for mid in model_ids() if (Path(__file__).with_name('model_manifest.json' if mid == DEFAULT_MODEL else 'model_manifest_1.7b.json')).is_file())

class PreparationError(Exception):
    pass

class Preparation:
    def __init__(self,home,settings=None,auth=None,drive_factory=Drive,*,model_id=DEFAULT_MODEL):
        self.home=Path(home)
        self.model_id=model_id
        self.segment=segment(model_id) if model_id != DEFAULT_MODEL else MODEL_SEGMENT
        self.settings=settings or {}
        self.auth=auth
        self.drive_factory=drive_factory
        self.base=self.home/'preparations'
        if model_id != DEFAULT_MODEL:self.base=self.base/model_id
        self.current=self.base/'current.json'

    def _busy(self):
        if ACTIVE.locked():return True
        path=self.base/'preparation.lock'
        if not path.exists():return False
        try:
            with path.open('r+b') as handle:
                if os.name=='nt':
                    import msvcrt
                    handle.seek(0)
                    try:msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
                    except OSError:return True
                    handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
                else:
                    import fcntl
                    try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    except OSError:return True
                    fcntl.flock(handle,fcntl.LOCK_UN)
        except OSError:return True
        return False

    def _load(self):
        if self.current.is_file():
            try:
                value=json.loads(self.current.read_text(encoding='utf8'))
                # A persisted nonterminal run is not silently called complete after restart.
                if value.get('status') in ('downloading','verifying') and not self._busy():
                    value.update(status='interrupted',error='process_interrupted')
                return value
            except (ValueError,OSError):
                pass
        return dict(id=None,status='idle',downloaded_bytes=0,total_bytes=0,current_file=None,files_verified=0,files=[],configuration='unverified',integrity='unverified',runtime='unverified',execution='not_run',error=None)

    def _save(self,state,run=None):
        self.base.mkdir(parents=True,exist_ok=True)
        encoded=json.dumps(state,ensure_ascii=False,indent=2)
        atomic_text(self.current,encoded)
        if run:
            atomic_text(run/'state.json',encoded)

    def _observed(self):
        if not (self.home/'inventory.sqlite3').is_file():
            return []
        with Inventory(self.home).connect() as db:
            latest=db.execute("SELECT scan_id,settings_json FROM scans WHERE account='B' ORDER BY started_at DESC,scan_id DESC LIMIT 1").fetchone()
            if not latest:return []
            snapshot=json.loads(latest['settings_json'])
            approved={(r['account'],r['id']) for r in self.settings.get('allowlist',[])}
            prior={(r['account'],r['id']) for r in snapshot.get('allowlist',[])}
            if not approved or not prior.issubset(approved):return []
            result=[]
            for row in db.execute('SELECT * FROM files WHERE scan_id=?',(latest['scan_id'],)):
                if self.segment in row['path'].split('/'):
                    result.append(dict(row)|{'metadata':json.loads(row['metadata_json'])})
            return result

    def plan(self):
        m=manifest(self.model_id); rows=self._observed(); roots=set()
        for row in rows:
            parts=row['path'].split('/'); index=parts.index(self.segment)
            if len(parts)==index+2:
                roots.update(row['metadata'].get('parents',[]))
        blockers=[]
        if not roots:blockers.append('model_not_found')
        if len(roots)>1:blockers.append('ambiguous_model')
        total=sum(f['size'] for f in m['files'])
        free=shutil.disk_usage(self.home).free
        required=total+512*1024*1024
        if free<required:blockers.append('insufficient_disk')
        return dict(status='blocked' if blockers else 'available',files=[dict(f,origin='official_model_component' if f.get('official_supplement') else 'designated_drive_component') for f in m['files']],total_bytes=total,required_bytes=required,free_bytes=free,blockers=blockers)

    def environment(self):
        from .runtime_paths import runtime_directory
        runtime=runtime_directory(self.home)
        record=runtime/'environment.json'
        if not record.is_file():return dict(status='unverified',blockers=['runtime_not_checked'])
        try:
            value=json.loads(record.read_text(encoding='utf8'))
            if runtime.name != 'runtime' and value.get('runtime_instance_id') != runtime.name:
                value.update(status='blocked',blockers=['runtime_record_invalid'])
            if not (runtime/'venv'/'Scripts'/'python.exe').is_file():
                value.update(status='blocked',blockers=['runtime_dependency_missing'])
            return {k:v for k,v in value.items() if k in ('status','python','packages','cuda_available','device','blockers','checked_at','probe_sha256','runtime_instance_id')}
        except (OSError,ValueError):return dict(status='blocked',blockers=['runtime_record_invalid'])

    def snapshot(self):
        m=manifest(self.model_id); state=self._load(); state.pop('pid',None)
        state['files']=[dict(f,origin='official_model_component' if f.get('official_supplement') else 'designated_drive_component') for f in state.get('files',[])]
        if state.get('status')=='ready':
            try:
                if not re.fullmatch('[a-f0-9]{32}',state['id']):raise ValueError()
                for item in state['files']:
                    asset=self.base/state['id']/'assets'/safe_relative(item['path'])
                    stat=asset.stat()
                    if not asset.is_file() or stat.st_size!=item['size'] or list((stat.st_size,stat.st_mtime_ns))!=item.get('verified_stat'):
                        raise ValueError()
            except (OSError,ValueError,KeyError):
                state.update(status='failed',integrity='unverified',error='local_asset_changed')
        env=self.environment(); state['runtime']=env['status'];state['environment']=env
        return dict(supported_model={k:m[k] for k in ('name','revision')}|{'id':m['model_id']},plan=self.plan(),preparation=state)

    def _check_ancestry(self,drive,folder):
        roots={r['id'] for r in self.settings.get('allowlist',[]) if r['account']=='B'}
        visited=set()
        for _ in range(40):
            if folder in visited:break
            visited.add(folder)
            data=drive.metadata(folder)
            if data.get('mimeType')!=FOLDER or data.get('trashed') or data.get('driveId'):break
            if folder in roots:return
            parents=data.get('parents',[])
            if len(parents)!=1:break
            folder=parents[0]
        raise PreparationError('outside_allowlist')

    def _mapping(self,drive,m):
        rows=self._observed();roots=set()
        for row in rows:
            parts=row['path'].split('/');i=parts.index(self.segment)
            if len(parts)==i+2:roots.update(row['metadata'].get('parents',[]))
        if len(roots)!=1:raise PreparationError('ambiguous_model' if roots else 'model_not_found')
        root=next(iter(roots));self._check_ancestry(drive,root)
        mapping={};directories={'':root}
        for prefix in ('','speech_tokenizer'):
            if prefix not in directories:raise PreparationError('missing_component')
            folder=directories[prefix];token=None;seen=set()
            while True:
                page=drive.children(folder,token)
                if page.get('incompleteSearch'):raise PreparationError('partial_source_listing')
                for item in page.get('files',[]):
                    if folder not in item.get('parents',[]) or item.get('trashed') or item.get('driveId'):continue
                    name=item.get('name','')
                    if '/' in name:raise PreparationError('unsafe_path')
                    safe_relative(name)
                    path=prefix+'/'+name if prefix else name
                    if item.get('mimeType')==FOLDER:
                        if path=='speech_tokenizer':
                            if path in directories:raise PreparationError('ambiguous_model')
                            directories[path]=item['id']
                    elif path in {f['path'] for f in m['files']}:
                        if path in mapping:raise PreparationError('ambiguous_component')
                        mapping[path]=item
                token=page.get('nextPageToken')
                if not token:break
                if token in seen:raise PreparationError('partial_source_listing')
                seen.add(token)
        for f in m['files']:
            item=mapping.get(f['path'])
            if not item:raise PreparationError('missing_component')
            expected=f.get('official_supplement',{}).get('observed_drive_bytes',f['size'])
            if str(item.get('size'))!=str(expected):raise PreparationError('source_changed')
        return mapping

    def prepare_local(self, source_directory, cancel=None):
        """Explicit designated model files only; new bytes, hashes and provenance."""
        from .inference import FileOwner, regular
        cancel = cancel or threading.Event()
        if not ACTIVE.acquire(False): raise PreparationError('operation_running')
        owner = None; run = None; state = None
        try:
            source = Path(source_directory)
            if not source.is_absolute() or '..' in source.parts: raise PreparationError('unsafe_local_path')
            regular(source, Path(source.anchor))
            if not source.is_dir(): raise PreparationError('source_missing')
            regular(self.base, self.home)
            self.base.mkdir(parents=True, exist_ok=True)
            owner = FileOwner(self.base/'preparation.lock')
            if not owner.handle: raise PreparationError('operation_running')
            m = manifest(self.model_id); run_id = uuid.uuid4().hex
            run = self.base/run_id; run.mkdir(exist_ok=False)
            state = dict(id=run_id,pid=os.getpid(),status='verifying',downloaded_bytes=0,total_bytes=sum(f['size'] for f in m['files']),current_file=None,files_verified=0,files=[dict(f,downloaded_bytes=0,status='pending',origin='designated_local_model_component') for f in m['files']],configuration='unverified',integrity='unverified',runtime='unverified',execution='not_run',error=None,started_at=now())
            self._save(state,run)
            provenance = dict(run_id=run_id,model=m['name'],revision=m['revision'],source=m['source'],kind='explicit_designated_local_model_components',source_directory=str(source),
                              configuration_source_sha256=[s['sha256'] for s in self.settings.get('sources', [])],files=[])
            state.update(model_id=self.model_id, source_directory=str(source))
            atomic_text(run/'inputs.json',json.dumps(provenance,indent=2))
            self._save(state,run)
            for item in state['files']:
                if cancel.is_set(): raise PreparationError('cancelled')
                relative = safe_relative(item['path'])
                state['preflight'] = dict(component=item['path'],expected_bytes=item['size'],observed_bytes=None)
                self._save(state,run)
                original = regular(source/relative, Path(source.anchor))
                if not original.is_file(): raise PreparationError('missing_component')
                before = original.stat()
                state['preflight']['observed_bytes'] = before.st_size
                self._save(state,run)
                if before.st_size != item['size']: raise PreparationError('size_mismatch')
                target = regular(run/'assets'/relative,self.home); target.parent.mkdir(parents=True,exist_ok=True)
                part = target.with_name(target.name+'.part')
                state['current_file'] = item['path']; self._save(state,run)
                sha = hashlib.sha256(); count = 0
                with original.open('rb') as incoming, part.open('xb') as outgoing:
                    for block in iter(lambda: incoming.read(1024*1024), b''):
                        if cancel.is_set(): raise PreparationError('cancelled')
                        count += len(block)
                        if count > item['size']: raise PreparationError('size_mismatch')
                        outgoing.write(block); sha.update(block)
                    outgoing.flush(); os.fsync(outgoing.fileno())
                after = original.stat(); regular(original,Path(source.anchor))
                if (before.st_size,before.st_mtime_ns) != (after.st_size,after.st_mtime_ns): raise PreparationError('source_changed')
                if count != item['size']: raise PreparationError('size_mismatch')
                if sha.hexdigest() != item['sha256']: raise PreparationError('hash_mismatch')
                os.link(part,target); part.unlink()
                stat = target.stat(); item.update(status='verified',downloaded_bytes=count,verified_stat=[stat.st_size,stat.st_mtime_ns])
                state['downloaded_bytes'] += count; state['files_verified'] += 1
                provenance['files'].append(dict(path=item['path'],size=count,sha256=sha.hexdigest(),origin='designated_local_model_component'))
                atomic_text(run/'inputs.json',json.dumps(provenance,indent=2)); self._save(state,run)
            if cancel.is_set(): raise PreparationError('cancelled')
            state.update(status='ready',configuration='complete',integrity='matched',current_file=None,finished_at=now())
            self._save(state,run)
            return state
        except Exception as error:
            if state is not None:
                code = str(error)
                state.update(status='cancelled' if code == 'cancelled' else 'failed',error=code if re.fullmatch('[a-z0-9_]+',code) else 'preparation_io_failed',finished_at=now())
                self._save(state,run)
            raise
        finally:
            if owner: owner.close()
            ACTIVE.release()

    def prepare(self,cancel=None):
        from .local_mode import is_local
        if is_local(self.settings): raise PreparationError('drive_setup_required')
        if not ACTIVE.acquire(False):raise PreparationError('operation_running')
        try:
            self.base.mkdir(parents=True,exist_ok=True)
            lockfile=(self.base/'preparation.lock').open('a+b')
        except OSError:
            ACTIVE.release()
            raise PreparationError('preparation_io_failed') from None
        try:
            if os.name=='nt':
                import msvcrt
                lockfile.seek(0);lockfile.write(b'0');lockfile.flush();lockfile.seek(0)
                msvcrt.locking(lockfile.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(lockfile,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            lockfile.close();ACTIVE.release();raise PreparationError('operation_running') from None
        cancel=cancel or threading.Event();run=None;state=self._load()
        try:
            plan=self.plan()
            if plan['blockers']:raise PreparationError(plan['blockers'][0])
            m=manifest(self.model_id);run_id=uuid.uuid4().hex
            self.base.mkdir(parents=True,exist_ok=True)
            run=self.base/run_id;run.mkdir(exist_ok=False)
            state=dict(id=run_id,pid=os.getpid(),status='downloading',downloaded_bytes=0,total_bytes=plan['total_bytes'],current_file=None,files_verified=0,files=[dict(f,downloaded_bytes=0,status='pending') for f in m['files']],configuration='unverified',integrity='unverified',runtime='unverified',execution='not_run',error=None,started_at=now())
            self._save(state,run)
            drive=self.drive_factory(lambda force_refresh=False:self.auth.access('B',force_refresh=force_refresh),cancel=cancel)
            sources=self._mapping(drive,m)
            provenance=dict(run_id=run_id,model=m['name'],revision=m['revision'],source=m['source'],files=sources,
                            origins={f['path']:dict(kind='official_model_component', **f['official_supplement']) if f.get('official_supplement') else dict(kind='designated_drive_component',drive_file_id=sources[f['path']]['id']) for f in m['files']})
            (run/'inputs.json').write_text(json.dumps(provenance,indent=2),encoding='utf8')
            paths=set();last_progress=0.0
            for f in state['files']:
                relative=safe_relative(f['path'])
                if str(relative).casefold() in paths:raise PreparationError('unsafe_path')
                paths.add(str(relative).casefold())
                if cancel.is_set():raise Cancelled('cancelled')
                source=sources[f['path']];fresh=drive.metadata(source['id'])
                for field in ('id','name','parents','size','version','modifiedTime','md5Checksum','sha1Checksum','sha256Checksum'):
                    if fresh.get(field)!=source.get(field):raise PreparationError('source_changed')
                if fresh.get('trashed') or fresh.get('driveId'):raise PreparationError('source_changed')
                state['current_file']=f['path'];f['status']='downloading'
                target=run/'assets'/relative;target.parent.mkdir(parents=True,exist_ok=True)
                part=target.with_name(target.name+'.part')
                sha=hashlib.sha256();md5=hashlib.md5();sha1=hashlib.sha1();size=0
                with part.open('xb') as output:
                    stream = self._official_content(f, cancel) if f.get('official_supplement') else drive.content(source['id'], size=f['size']) if isinstance(drive, Drive) else drive.content(source['id'])
                    for chunk in stream:
                        if cancel.is_set():raise Cancelled('cancelled')
                        if shutil.disk_usage(run).free < len(chunk)+64*1024*1024:raise PreparationError('insufficient_disk')
                        size+=len(chunk)
                        if size>f['size']:raise PreparationError('size_mismatch')
                        output.write(chunk);sha.update(chunk);md5.update(chunk);sha1.update(chunk)
                        state['downloaded_bytes']+=len(chunk);f['downloaded_bytes']=size
                        if time.monotonic()-last_progress>=0.5:
                            self._save(state,run);last_progress=time.monotonic()
                    output.flush();os.fsync(output.fileno())
                if cancel.is_set():raise Cancelled('cancelled')
                state['status']='verifying';self._save(state,run)
                if size!=f['size']:raise PreparationError('size_mismatch')
                if sha.hexdigest()!=f['sha256']:raise PreparationError('hash_mismatch')
                for field,digest in (('md5Checksum',md5),('sha1Checksum',sha1),('sha256Checksum',sha)):
                    if not f.get('official_supplement') and fresh.get(field) and fresh[field]!=digest.hexdigest():raise PreparationError('hash_mismatch')
                after=drive.metadata(source['id'])
                if any(after.get(k)!=fresh.get(k) for k in ('id','version','modifiedTime','size','parents','name','md5Checksum','sha1Checksum','sha256Checksum','driveId','mimeType')) or after.get('trashed'):raise PreparationError('source_changed')
                # New destination only: link fails rather than replacing an existing file.
                os.link(part,target);part.unlink()
                stat=target.stat();f['verified_stat']=[stat.st_size,stat.st_mtime_ns]
                f['status']='verified';state['files_verified']+=1;state['status']='downloading';self._save(state,run)
            if cancel.is_set():raise Cancelled('cancelled')
            state.update(status='ready',configuration='complete',integrity='matched',current_file=None,finished_at=now())
        except Cancelled:
            state.update(status='cancelled',error='cancelled',finished_at=now())
        except (PreparationError,DriveError,ValueError) as error:
            code=str(error)
            state.update(status='failed',error=code if re.fullmatch('[a-z0-9_]+',code) else 'preparation_failed',finished_at=now())
            if code=='hash_mismatch':state['integrity']='mismatched'
            if code=='missing_component':state['configuration']='missing'
        except Exception as error:
            state.update(status='failed',error='preparation_io_failed',finished_at=now())
            if run:
                diagnostic=dict(exception_type=type(error).__name__,errno=getattr(error,'errno',None),winerror=getattr(error,'winerror',None),operation='prepare',recorded_at=now())
                try:atomic_text(run/'failure.json',json.dumps(diagnostic,indent=2))
                except OSError:pass
        finally:
            try:self._save(state,run)
            finally:
                lockfile.close()
                ACTIVE.release()
        return self.snapshot()['preparation']

    def _official_content(self, item, cancel):
        # Only this pinned, explicitly approved configuration supplement is allowed.
        supplement=item['official_supplement'];m=manifest(self.model_id)
        expected='https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice/resolve/'+m['revision']+'/speech_tokenizer/config.json'
        if self.model_id!='qwen3-tts-1.7b-customvoice' or item['path']!='speech_tokenizer/config.json' or supplement['url']!=expected or item['size']!=2336 or item['sha256']!='ee65bb901c876664ab8707c487157aa1a6ee57c65969b28fb5ec9dc211e68167':
            raise PreparationError('unsupported_supplement')
        try:
            with requests.Session() as session:
                session.trust_env=False
                # No Drive credentials or user model tokens enter the public request.
                with session.get(expected,stream=True,timeout=(15,60)) as response:
                    if response.status_code!=200:raise PreparationError('official_component_unavailable')
                    for chunk in response.iter_content(64*1024):
                        if cancel.is_set():raise Cancelled('cancelled')
                        if chunk:yield chunk
        except requests.RequestException:
            raise PreparationError('official_component_unavailable') from None

    def probe_runtime(self):
        from .runtime_paths import runtime_directory
        runtime=runtime_directory(self.home)
        python=runtime/'venv'/'Scripts'/'python.exe'
        probe=Path(__file__).with_name('runtime_probe.py')
        if not python.is_file():
            value=dict(status='blocked',blockers=['runtime_dependency_missing'])
        else:
            try:
                env=os.environ.copy();env.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
                from .external_process import run_external
                result=run_external([str(python),str(probe)],capture_output=True,text=True,timeout=120,env=env)
                value=json.loads(result.stdout) if result.returncode==0 else dict(status='blocked',blockers=['runtime_probe_failed'])
            except (OSError,ValueError,subprocess.TimeoutExpired):value=dict(status='blocked',blockers=['runtime_probe_failed'])
        value.update(checked_at=now(),probe_sha256=hashlib.sha256(probe.read_bytes()).hexdigest(),runtime_instance_id=runtime.name)
        record=runtime/'environment.json';atomic_text(record,json.dumps(value,indent=2))
        return value
