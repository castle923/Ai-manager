"""Explicit local model catalogue. Observations never imply verified execution."""
from contextlib import contextmanager, closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import uuid

from .config import private_home
from .dashboard import Dashboard
from .models import model_ids as tts_model_ids, manifest_path as tts_manifest_path
from .preparation import manifest as tts_manifest
from . import adapters

def model_ids(): return tts_model_ids() + adapters.configured_ids()
def manifest_path(identifier): return tts_manifest_path(identifier) if identifier in tts_model_ids() else adapters.manifest_path(identifier)
def manifest(identifier): return tts_manifest(identifier) if identifier in tts_model_ids() else adapters.manifest(identifier)


SCHEMA = """CREATE TABLE models (
 id TEXT PRIMARY KEY, row_version INTEGER NOT NULL, created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL, archived INTEGER NOT NULL DEFAULT 0,
 metadata_json TEXT NOT NULL, artifact_json TEXT NOT NULL,
 generation TEXT NOT NULL, fingerprint TEXT NOT NULL);
CREATE TABLE model_references (
 model_id TEXT NOT NULL REFERENCES models(id), identity TEXT NOT NULL,
 reference_json TEXT NOT NULL, PRIMARY KEY(model_id,identity));
"""


class RegistryError(ValueError):
    pass


def stamp():
    return datetime.now(timezone.utc).isoformat()


def packed(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def sha(value):
    return hashlib.sha256(packed(value).encode()).hexdigest()


def text(value, maximum, required=False):
    if not isinstance(value, str) or len(value) > maximum or any(ord(c) < 32 and c not in '\n\t' for c in value):
        raise RegistryError('invalid_metadata')
    value = value.strip()
    try: value.encode('utf8')
    except UnicodeEncodeError: raise RegistryError('invalid_metadata') from None
    if required and not value:
        raise RegistryError('name_required')
    return value


class Registry:
    def __init__(self, home, settings=None, inference=None, tasks=None):
        self.home = private_home(Path(home))
        self.home.mkdir(parents=True, exist_ok=True)
        self.path = self.home / 'registry.sqlite3'
        private_home(self.path)
        self.settings, self.inference, self.tasks = settings, inference, tasks
        # A distinct database preserves the inventory and its existing recovery contract.
        with self.connect() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1):
                raise RegistryError('registry_schema_unsupported')
            if version == 0:
                tables = db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
                if tables:
                    raise RegistryError('registry_schema_unsupported')
                # DDL and version marker share one transaction; no partially published schema.
                for statement in SCHEMA.split(';'):
                    if statement.strip(): db.execute(statement)
                db.execute('PRAGMA user_version=1')
            def schema(connection):
                return [tuple(r) for r in connection.execute("SELECT type,name,sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type,name")]
            with closing(sqlite3.connect(':memory:')) as expected:
                expected.executescript(SCHEMA)
                if schema(db) != schema(expected): raise RegistryError('registry_schema_unsupported')

    @contextmanager
    def connect(self):
        with closing(sqlite3.connect(self.path, timeout=10)) as db:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('BEGIN IMMEDIATE')
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

    def _metadata(self, value):
        fields = {'name', 'type', 'description', 'version_label', 'tags', 'notes'}
        if not isinstance(value, dict) or set(value) != fields:
            raise RegistryError('invalid_metadata')
        tags = value['tags']
        if not isinstance(tags, list) or len(tags) > 20 or any(not isinstance(t, str) for t in tags):
            raise RegistryError('invalid_metadata')
        return {k: text(value[k], 200 if k in {'name','type','version_label'} else 3000, k == 'name') for k in fields - {'tags'}} | {
            'tags': list(dict.fromkeys(text(t, 60, True) for t in tags))}

    def _artifact(self, value):
        if not isinstance(value, dict) or set(value) != {'adapter_id', 'revision'}:
            raise RegistryError('invalid_artifact')
        adapter, revision = value['adapter_id'], value['revision']
        if not isinstance(adapter, str) or not isinstance(revision, str) or len(revision) > 200:
            raise RegistryError('invalid_artifact')
        if not adapter:
            return {'adapter_id': '', 'revision': revision, 'manifest_sha256': None}
        if adapter not in model_ids() or revision != manifest(adapter)['revision']:
            raise RegistryError('unsupported_artifact')
        return {'adapter_id': adapter, 'revision': revision,
                'manifest_sha256': hashlib.sha256(manifest_path(adapter).read_bytes()).hexdigest()}

    def _references(self, value, retained=()):
        if not isinstance(value, list) or len(value) > 20:
            raise RegistryError('invalid_references')
        result = []
        for ref in value:
            if not isinstance(ref, dict): raise RegistryError('invalid_references')
            if set(ref) == {'existing_identity'}:
                identity = ref['existing_identity']
                matches = [r for r in retained if isinstance(identity,str) and r['identity']==identity]
                if len(matches)!=1: raise RegistryError('invalid_references')
                result.append(matches[0])
                continue
            if ref in retained:
                result.append(ref)
                continue
            if set(ref) == {'candidate_id', 'scan_id'}:
                if not isinstance(ref['candidate_id'],str) or not re.fullmatch('[a-f0-9]{24}',ref['candidate_id']) or not isinstance(ref['scan_id'],str) or not 0<len(ref['scan_id'])<=100:
                    raise RegistryError('invalid_references')
                try:
                    candidate = Dashboard(self.home, read_only=True).detail(ref['candidate_id'], ref['scan_id'])
                except (ValueError, KeyError, TypeError, sqlite3.DatabaseError):
                    raise RegistryError('candidate_not_found') from None
                files = candidate.get('files', [candidate])
                account = candidate['account']
                with closing(sqlite3.connect((self.home/'inventory.sqlite3').as_uri()+'?mode=ro',uri=True)) as source:
                    scan = source.execute('SELECT settings_json FROM scans WHERE scan_id=?',(ref['scan_id'],)).fetchone()
                observed_roots = {r['alias']:r['id'] for r in json.loads(scan[0]).get('allowlist',[]) if r['account']==account}
                if len(observed_roots)!=sum(r['account']==account for r in json.loads(scan[0]).get('allowlist',[])):
                    raise RegistryError('reference_scope_ambiguous')
                allowed = {(r['alias'],r['id']) for r in (self.settings or {}).get('allowlist', []) if r['account'] == account}
                if not files or any((f['root'],observed_roots.get(f['root'])) not in allowed for f in files):
                    raise RegistryError('reference_out_of_scope')
                components = []
                for f in files:
                    components.append({k: f[k] for k in ('file_id','name','path','root','kind','size','modified')})
                    components[-1]['root_id'] = observed_roots[f['root']]
                identity = 'drive:' + account + ':' + (candidate.get('folder_id') or candidate['file_id'])
                if candidate.get('folder_id','').startswith('ambiguous:'): raise RegistryError('candidate_reference_ambiguous')
                result.append(dict(kind='drive', identity=identity, account=account,
                                   scan_id=ref['scan_id'], path=candidate['path'], components=components,
                                   observation_status=candidate['scan_status']))
            elif set(ref) == {'local_directory'}:
                raw = ref['local_directory']
                if not isinstance(raw, str) or not raw or len(raw) > 32767 or '\n' in raw or '\x00' in raw:
                    raise RegistryError('invalid_local_reference')
                try: directory = private_home(Path(raw))
                except (ValueError, OSError): raise RegistryError('invalid_local_reference') from None
                if not directory.is_dir(): raise RegistryError('local_directory_missing')
                # User-selected location only. No recursive discovery, reads, downloads or execution.
                result.append(dict(kind='local', identity='local:' + str(directory).casefold(), path=str(directory),
                                   components=[], observation_status='unverified'))
            else:
                raise RegistryError('invalid_references')
        if len({r['identity'] for r in result}) != len(result):
            raise RegistryError('duplicate_reference')
        return sorted(result, key=lambda r:r['identity'])

    def _attest(self, refs, artifact):
        """Explicitly hash only the selected adapter's declared components, never arbitrary files."""
        from .inference import digest, regular
        from .preparation import safe_relative
        if not artifact['adapter_id']: return refs
        expected = manifest(artifact['adapter_id'])['files']
        result=[]
        for original in refs:
            ref=dict(original)
            if ref['kind']=='local':
                components=[]
                matched=True
                root=private_home(Path(ref['path']))
                for item in expected:
                    observed=dict(name=item['path'],kind='model_component',expected_bytes=item['size'],expected_sha256=item['sha256'],size=None,sha256=None,mtime_ns=None)
                    try:
                        path=regular(root/safe_relative(item['path']),root)
                        if path.is_file():
                            info=path.stat(); observed.update(size=info.st_size,mtime_ns=info.st_mtime_ns)
                            if info.st_size==item['size']: observed['sha256']=digest(path)
                    except (OSError,ValueError): pass
                    if observed['size']!=item['size'] or observed['sha256']!=item['sha256']: matched=False
                    components.append(observed)
                ref.update(components=components,artifact_match=matched,bound_manifest_sha256=artifact['manifest_sha256'],checked_at=stamp())
            result.append(ref)
        return result

    def _local_match(self, ref, artifact):
        from .inference import regular
        from .preparation import safe_relative
        if ref['kind']!='local' or not ref.get('artifact_match') or ref.get('bound_manifest_sha256')!=artifact['manifest_sha256']: return False
        try:
            root=private_home(Path(ref['path']))
            expected=manifest(artifact['adapter_id'])['files']
            components=ref['components']
            if len(components)!=len(expected): return False
            for item,c in zip(expected,components):
                if c['name']!=item['path'] or c['sha256']!=item['sha256']: return False
                path=regular(root/safe_relative(item['path']),root)
                info=path.stat()
                if not path.is_file() or info.st_size!=item['size'] or info.st_mtime_ns!=c['mtime_ns']: return False
            return True
        except (OSError,ValueError,KeyError): return False

    @staticmethod
    def _fingerprint(artifact, refs):
        # Scan IDs are observation IDs, never model or artifact identities.
        stable=[]
        for r in refs:
            value={k:v for k,v in r.items() if k not in {'scan_id','observation_status','checked_at'}}
            value['components']=[{k:v for k,v in c.items() if k!='mtime_ns'} for c in r['components']]
            stable.append(value)
        return sha({'artifact': artifact, 'references': stable})

    def _row(self, db, identifier):
        if not isinstance(identifier, str) or not re.fullmatch('[a-f0-9]{32}', identifier):
            raise RegistryError('model_not_found')
        row = db.execute('SELECT * FROM models WHERE id=?', (identifier,)).fetchone()
        if row is None: raise RegistryError('model_not_found')
        refs = [json.loads(r[0]) for r in db.execute('SELECT reference_json FROM model_references WHERE model_id=? ORDER BY identity', (identifier,))]
        return dict(row) | {'metadata': json.loads(row['metadata_json']), 'artifact': json.loads(row['artifact_json']), 'references': refs}

    def _write_refs(self, db, identifier, refs):
        archived = db.execute('SELECT archived FROM models WHERE id=?',(identifier,)).fetchone()[0]
        if not archived:
            for ref in refs:
                duplicate = db.execute('SELECT r.model_id FROM model_references r JOIN models m ON m.id=r.model_id WHERE r.identity=? AND m.archived=0 AND r.model_id!=?', (ref['identity'],identifier)).fetchone()
                if duplicate: raise RegistryError('duplicate_reference')
        db.execute('DELETE FROM model_references WHERE model_id=?', (identifier,))
        db.executemany('INSERT INTO model_references VALUES(?,?,?)', [(identifier,r['identity'],packed(r)) for r in refs])

    def create(self, data):
        if not isinstance(data, dict) or set(data) != {'metadata','artifact','references'}:
            raise RegistryError('invalid_request')
        metadata, artifact, refs = self._metadata(data['metadata']), self._artifact(data['artifact']), self._references(data['references'])
        refs=self._attest(refs,artifact)
        identifier, generation, created = uuid.uuid4().hex, uuid.uuid4().hex, stamp()
        with self.connect() as db:
            db.execute('INSERT INTO models VALUES(?,1,?,?,0,?,?,?,?)', (identifier,created,created,packed(metadata),packed(artifact),generation,self._fingerprint(artifact,refs)))
            self._write_refs(db,identifier,refs)
        return self.get(identifier)

    def update(self, identifier, data):
        if not isinstance(data, dict) or set(data) != {'row_version','metadata','artifact','references','archived'} or type(data['row_version']) is not int or type(data['archived']) is not bool:
            raise RegistryError('invalid_request')
        metadata, artifact = self._metadata(data['metadata']), self._artifact(data['artifact'])
        # Existing frozen references may be retained without pretending they were reobserved.
        with self.connect() as db:
            old = self._row(db, identifier)
            if old['row_version'] != data['row_version']: raise RegistryError('stale_edit')
            if data['references'] == old['references']:
                refs = old['references']
            else:
                refs = self._references(data['references'],old['references'])
            if artifact!=old['artifact'] or refs!=old['references']:
                refs=self._attest(refs,artifact)
            fingerprint = self._fingerprint(artifact,refs)
            generation = old['generation'] if fingerprint == old['fingerprint'] and old['archived'] == int(data['archived']) else uuid.uuid4().hex
            db.execute('UPDATE models SET metadata_json=?,artifact_json=?,fingerprint=?,generation=?,archived=?,updated_at=?,row_version=row_version+1 WHERE id=? AND row_version=?',
                       (packed(metadata),packed(artifact),fingerprint,generation,int(data['archived']),stamp(),identifier,data['row_version']))
            self._write_refs(db,identifier,refs)
        return self.get(identifier)

    def _public(self, row):
        result = {k: row[k] for k in ('id','row_version','created_at','updated_at','generation','fingerprint','metadata','artifact','references')}
        result['archived'] = bool(row['archived'])
        reasons = []
        adapter = row['artifact']['adapter_id']
        if not row['references']: reasons.append('references_unconfirmed')
        for ref in row['references']:
            if ref['kind'] == 'local':
                try: exists = private_home(Path(ref['path'])).is_dir()
                except (ValueError,OSError): exists = False
                if not exists: reasons.append('local_location_unavailable')
            elif self.settings is not None:
                roots = {(r['alias'],r['id']) for r in self.settings.get('allowlist', []) if r['account'] == ref['account']}
                if any((c['root'],c.get('root_id')) not in roots for c in ref['components']): reasons.append('reference_out_of_scope')
        if not adapter: reasons.append('configuration_unconfirmed')
        elif row['artifact']['manifest_sha256'] != hashlib.sha256(manifest_path(adapter).read_bytes()).hexdigest(): reasons.append('artifact_revision_changed')
        if adapter and not any(self._local_match(ref,row['artifact']) for ref in row['references']): reasons.append('artifact_files_unconfirmed')
        # Inventory observations and a local directory's existence never prove file integrity.
        result['configuration_attention'] = bool(reasons)
        result['configuration_reasons'] = list(dict.fromkeys(reasons))
        result['execution'] = 'unexecuted'
        result['latest_run_status'] = None
        result['verification_scope'] = 'registered_artifact_at_recorded_execution_time'
        result['preparation'] = 'unconfirmed'
        result['runtime'] = 'unconfirmed'
        result['integrity'] = 'unverified'
        if adapter and any(self._local_match(ref,row['artifact']) for ref in row['references']): result['integrity']='recorded_hash_match'
        result['task_type'] = adapters.descriptor(adapter)['task_type'] if adapter in adapters.CATALOG else 'tts'
        execution_blocker = adapters.descriptor(adapter).get('blocker') if adapter in adapters.CATALOG else None
        result['execution_target'] = 'local'
        result['execution_advisories'] = [execution_blocker] if execution_blocker else []
        if adapter and adapter in adapters.CATALOG and not reasons:
            from .task_runtime import environment
            result['preparation'] = 'recorded_ready'
            result['runtime'] = environment(self.home, adapter)['status']
        if adapter and adapter not in adapters.CATALOG and not reasons:
            from .preparation import Preparation
            from .inference import regular
            from .preparation import safe_relative
            prep=Preparation(self.home, model_id=adapter)
            state = prep._load()
            if state.get('status') == 'ready' and state.get('integrity') == 'matched':
                try:
                    if not re.fullmatch('[a-f0-9]{32}',state.get('id','')): raise ValueError()
                    expected=manifest(adapter)['files']
                    files=state.get('files',[])
                    if len(expected)!=len(files): raise ValueError()
                    for item,saved in zip(expected,files):
                        if any(saved.get(k)!=item[k] for k in ('path','size','sha256')): raise ValueError()
                        path=regular(prep.base/state['id']/'assets'/safe_relative(item['path']),self.home)
                        info=path.stat()
                        if not path.is_file() or [info.st_size,info.st_mtime_ns]!=saved.get('verified_stat'): raise ValueError()
                    result['preparation'] = 'recorded_ready'
                except (OSError,ValueError,KeyError): pass
            result['runtime']=prep.environment().get('status','unconfirmed')
        result['runs'] = []
        executor = self.tasks if adapter in adapters.CATALOG else self.inference
        if executor:
            for run in executor.registry_runs(row['id']):
                binding = run.get('registry_binding') or {}
                current = binding.get('generation') == row['generation'] and binding.get('fingerprint') == row['fingerprint']
                verified = current and not reasons and executor.registry_verified(run, binding)
                result['runs'].append({'run':run, 'current_artifact':current, 'verified':verified})
            current_runs = [r for r in result['runs'] if r['current_artifact']]
            result['latest_run_status'] = current_runs[0]['run']['status'] if current_runs else None
            if any(r['verified'] for r in current_runs): result['execution'] = 'verified'
            elif any(r['run']['status'] not in {'succeeded','failed','cancelled','interrupted'} for r in current_runs): result['execution'] = 'running'
            elif current_runs: result['execution'] = 'failed' if current_runs[0]['run']['status'] == 'failed' else 'unverified'
        result['execution_blockers'] = (['configuration_required'] if reasons else []) + ([] if result['runtime']=='ready' else ['adapter_runtime_not_ready']) + (['model_archived'] if result['archived'] else [])
        result['execution_eligibility'] = 'blocked' if result['execution_blockers'] else 'requires_run_preflight'
        result['status'] = 'archived' if result['archived'] else 'running' if result['execution'] == 'running' else 'configuration_needed' if reasons else 'failed' if result['latest_run_status'] == 'failed' else 'verified' if result['execution'] == 'verified' else ('ready' if result['runtime']=='ready' else 'prepared') if result['preparation'] == 'recorded_ready' else 'unexecuted'
        return result

    def get(self, identifier):
        with self.connect() as db: row = self._row(db,identifier)
        return self._public(row)

    def query(self, q='', status='', include_archived=False):
        if not isinstance(q,str) or len(q)>300: raise RegistryError('invalid_query')
        with self.connect() as db:
            rows = [self._row(db,r[0]) for r in db.execute('SELECT id FROM models ORDER BY created_at DESC,id')]
        public = [self._public(row) for row in rows]
        active = [r for r in public if not r['archived']]
        filtered = [r for r in public if (include_archived or not r['archived']) and (not status or r['status']==status or status=='failed' and r['latest_run_status']=='failed') and
                    (not q or q.casefold() in ' '.join([r['metadata'][key] for key in ('name','type','description','version_label','notes')]+r['metadata']['tags']).casefold())]
        return {'models':filtered, 'summary':{'registered':len(active),'verified':sum(r['execution']=='verified' for r in active), 'configuration_needed':sum(r['configuration_attention'] for r in active)},
                'supported_artifacts':[{'adapter_id':m,'name':manifest(m)['name'],'revision':manifest(m)['revision']} for m in model_ids()]}

    def create_run(self, identifier, row_version, text_value):
        if self.inference is None: raise RegistryError('execution_unavailable')
        with self.connect() as db:
            row = self._row(db,identifier)
            if type(row_version) is not int or row['row_version'] != row_version: raise RegistryError('stale_edit')
            if row['archived']: raise RegistryError('model_archived')
            if not row['artifact']['adapter_id']: raise RegistryError('adapter_unsupported')
            if self._public(row)['configuration_attention']: raise RegistryError('configuration_required')
            fresh=self._attest(row['references'],row['artifact'])
            if self._fingerprint(row['artifact'],fresh)!=row['fingerprint'] or not any(self._local_match(r,row['artifact']) for r in fresh): raise RegistryError('artifact_files_changed')
            binding = {k:row[k] for k in ('id','generation','fingerprint')}
            binding['manifest_sha256'] = row['artifact']['manifest_sha256']
            binding['asset_sha256'] = sha([{k:i[k] for k in ('path','size','sha256')} for i in manifest(row['artifact']['adapter_id'])['files']])
            binding['registered_source'] = next(r['path'] for r in fresh if self._local_match(r,row['artifact']))
            if row['artifact']['adapter_id'] in adapters.CATALOG: raise RegistryError('typed_input_required')
            return self.inference.create_registered(text_value,row['artifact']['adapter_id'],binding)


    def create_task(self, identifier, row_version, payload):
        if self.tasks is None: raise RegistryError('execution_unavailable')
        with self.connect() as db:
            row=self._row(db,identifier)
            if type(row_version) is not int or row['row_version']!=row_version:raise RegistryError('stale_edit')
            if row['archived']:raise RegistryError('model_archived')
            adapter=row['artifact']['adapter_id']
            if adapter not in adapters.configured_ids():raise RegistryError('adapter_unsupported')
            if self._public(row)['configuration_attention']:raise RegistryError('configuration_required')
            fresh=self._attest(row['references'],row['artifact'])
            if self._fingerprint(row['artifact'],fresh)!=row['fingerprint'] or not any(self._local_match(r,row['artifact']) for r in fresh):raise RegistryError('artifact_files_changed')
            binding={k:row[k] for k in ('id','generation','fingerprint')}
            binding['manifest_sha256']=row['artifact']['manifest_sha256']
            binding['asset_sha256']=sha([{k:i[k] for k in ('path','size','sha256')} for i in manifest(adapter)['files']])
            binding['registered_source']=next(r['path'] for r in fresh if self._local_match(r,row['artifact']))
            return self.tasks.create_registered(payload,adapter,binding)
