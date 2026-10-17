"""Read-only, source-linked history snapshots and bounded task records."""
from datetime import datetime, timezone
import copy
import hashlib
import json
import math
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time
import uuid

from .config import private_home
from .inference import regular, digest
from .models import DEFAULT_MODEL, model_ids, load_manifest, manifest_path
from .runtime_paths import runtime_directory

KINDS={'scan','preparation','run','comparison','runtime','runtime_check','task'}
STATUSES={'queued','staged','preparing','loading','running','cancelling','succeeded','complete','completed','partial','failed','cancelled','interrupted','ready','blocked','verifying','downloading','finished','idle','unknown','not_started'}
ACTIONS={'connect','refresh','scan','disconnect','prepare','runtime_check'}
LABELS=dict(scan='Drive 수집',preparation='모델 파일 준비',run='음성 실행',comparison='A/B 비교',runtime='현재 런타임 준비 상태',runtime_check='현재 환경 점검 기록',task='앱 작업')


def comparison_projection(state, home):
    """Read the real raw serializer format without constructing a recovering engine."""
    identifiers = state.get('run_ids')
    order = (state.get('conditions') or {}).get('execution_order') if isinstance(state.get('conditions'), dict) else None
    if (state.get('admitted') is not True or not isinstance(identifiers, list) or len(identifiers) != 2
            or any(not isinstance(i, str) or not re.fullmatch('[a-f0-9]{32}', i) for i in identifiers)
            or len(set(identifiers)) != 2 or not isinstance(order, list) or len(order) != 2 or set(order) != set(model_ids())
            or not isinstance(state.get('text'), str) or not isinstance(state.get('parameters'), dict)
            or hashlib.sha256(state['text'].encode('utf8')).hexdigest() != state.get('input_sha256')):
        raise ValueError('invalid_comparison_record')
    terminal = {'succeeded', 'failed', 'cancelled', 'interrupted'}
    allowed = terminal | {'queued', 'staged', 'preparing', 'loading', 'running', 'cancelling'}
    runs = []
    for index, (identifier, side) in enumerate(zip(identifiers, ('A', 'B'))):
        run = read_record(home / 'tts' / identifier / 'state.json', home)
        if (run.get('id') != identifier or run.get('comparison_id') != state.get('id') or run.get('comparison_side') != side
                or run.get('text') != state['text'] or run.get('input_sha256') != state['input_sha256']
                or run.get('parameters') != state['parameters'] or not isinstance(run.get('model'), dict)
                or run['model'].get('id') != order[index] or not isinstance(run.get('status'), str) or run['status'] not in allowed
                or any(run.get(k) is not None and stamp(run[k]) is None for k in ('started_at', 'finished_at'))
                or (run['status'] in terminal and stamp(run.get('finished_at')) is None)):
            raise ValueError('invalid_comparison_child')
        runs.append(run)
    states = [run['status'] for run in runs]
    if any(value not in terminal for value in states):
        status = 'cancelling' if 'cancelling' in states else 'queued' if all(value in {'queued', 'staged'} for value in states) else 'running'
    elif all(value == 'succeeded' for value in states): status = 'completed'
    elif 'succeeded' in states: status = 'partial'
    elif 'interrupted' in states: status = 'interrupted'
    elif all(value == 'cancelled' for value in states): status = 'cancelled'
    else: status = 'failed'
    finished = max(stamp(run['finished_at']) for run in runs) if all(value in terminal for value in states) else None
    return dict(state, status=status, finished_at=finished)


class HistoryError(ValueError):pass


def stamp(value):
    """Only explicit aware instants enter the timeline. No mtime/date guessing."""
    try:
        if isinstance(value,str):dt=datetime.fromisoformat(value.replace('Z','+00:00'))
        elif type(value)in(int,float)and math.isfinite(value):dt=datetime.fromtimestamp(value,timezone.utc)
        else:return None
        if dt.tzinfo is None:return None
        return dt.astimezone(timezone.utc).isoformat()
    except (ValueError,OverflowError,OSError):return None


def number(value):
    return value if type(value)in(int,float)and 0<=value<=2**53-1 and math.isfinite(value)else None


def read_record(path,home):
    path=regular(path,home)
    if path.stat().st_size>8*1024*1024:raise ValueError('record_too_large')
    def invalid_constant(_):raise ValueError('nonfinite_record')
    value=json.loads(path.read_text(encoding='utf8'),parse_constant=invalid_constant)
    if not isinstance(value,dict):raise ValueError('invalid_record')
    return value


class History:
    def __init__(self,home):
        self.home=private_home(home)
        self.lock=threading.RLock()
        self.snapshots={}
        self.journal_failed=False

    def task_record(self,identifier,action,account,started_at,status,finished_at=None,has_error=False):
        """New M9 tasks only; never persist credentials, result bodies or raw errors."""
        if action not in ACTIONS or account not in ('A','B')or not re.fullmatch('[a-f0-9]{32}',identifier):return
        try:
            root=private_home(self.home/'task-history');root.mkdir(exist_ok=True)
            path=private_home(root/(identifier+'.json'))
            from .preparation import atomic_text
            private_home(path.with_suffix('.json.tmp'))
            atomic_text(path,json.dumps(dict(id=identifier,action=action,account=account,started_at=started_at,finished_at=finished_at,status=status,has_error=bool(has_error))))
        except (OSError,ValueError,TypeError):
            # The original operation remains authoritative; missing journal is visible as such.
            self.journal_failed=True

    @staticmethod
    def event(kind,identifier,state,details=None,*,current=False):
        start=stamp(state.get('started_at',state.get('created_at')))
        finish=stamp(state.get('finished_at',state.get('completed_at',state.get('checked_at'))))
        status=state.get('status')if isinstance(state.get('status'),str)and state['status']in STATUSES else 'unknown'
        return dict(key=kind+':'+identifier,kind=kind,id=identifier,label=LABELS[kind],status=status,
                    started_at=start,finished_at=finish,sort_at=start or finish,time_basis='started_at'if start else'finished_at'if finish else'not_recorded',
                    scope='current_state'if current else'recorded_history',read_error=False,has_error=bool(state.get('error')or state.get('has_error')),details=details or {})

    def _records(self):
        records=[];issues=['task_journal_unavailable']if self.journal_failed else[]
        database=self.home/'inventory.sqlite3'
        if database.exists():
            try:
                regular(database,self.home)
                with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True,timeout=1)as db:
                    db.row_factory=sqlite3.Row
                    for row in db.execute('SELECT scan_id,account,started_at,finished_at,status,files_count,folders_count,excluded_count FROM scans'):
                        v=dict(row)
                        valid_id=isinstance(v['scan_id'],str)and re.fullmatch('[a-f0-9]{32}',v['scan_id'])
                        valid=valid_id and v['account']in('A','B')and isinstance(v['status'],str)and v['status']in STATUSES and stamp(v['started_at'])is not None and(v['finished_at']is None or stamp(v['finished_at'])is not None)and all(type(v[k])is int and number(v[k])is not None for k in('files_count','folders_count','excluded_count'))
                        if valid:
                            records.append(self.event('scan',v['scan_id'],v,{k:v[k]for k in('account','files_count','folders_count','excluded_count')}))
                        else:
                            identifier=v['scan_id']if valid_id else hashlib.sha256(repr(tuple(row)).encode()).hexdigest()[:32]
                            event=self.event('scan',identifier,{});event.update(read_error=True,source_id_available=bool(valid_id));records.append(event)
            except (OSError,ValueError,sqlite3.DatabaseError):issues.append('scan_records_unavailable')
        paths=[]
        for kind,base in (('run',self.home/'tts'),('comparison',self.home/'comparisons'),('task',self.home/'task-history')):
            if base.exists():
                try:
                    regular(base,self.home)
                    if kind=='task':paths.extend((kind,p.stem,p,False)for p in base.glob('*.json'))
                    else:paths.extend((kind,p.name,p/'state.json',False)for p in base.iterdir()if p.is_dir())
                except (OSError,ValueError):issues.append(kind+'_records_unavailable')
        preparations=self.home/'preparations'
        if preparations.exists():
            try:
                regular(preparations,self.home)
                paths.extend(('preparation',p.name,p/'state.json',False)for p in preparations.iterdir()if p.is_dir())
                for mid in model_ids():
                    if mid!=DEFAULT_MODEL:
                        sub=regular(preparations/mid,self.home)
                        if sub.exists():paths.extend(('preparation',p.name,p/'state.json',False)for p in sub.iterdir()if p.is_dir())
            except (OSError,ValueError):issues.append('preparation_records_unavailable')
        # These are snapshots of the currently selected runtime, not invented historic attempts.
        try:
            runtime=runtime_directory(self.home)
            for kind,name in (('runtime','bootstrap.json'),('runtime_check','environment.json')):
                path=runtime/name
                if path.exists():paths.append((kind,runtime.name,path,True))
        except(OSError,ValueError):issues.append('runtime_records_unavailable')
        for kind,identifier,path,current in paths:
            if kind not in ('runtime','runtime_check')and not re.fullmatch('[a-f0-9]{32}',identifier):continue
            try:
                state=read_record(path,self.home)
                if kind not in ('runtime','runtime_check')and state.get('id')!=identifier:raise ValueError('identity_mismatch')
                if kind=='comparison':state=comparison_projection(state,self.home)
                if not isinstance(state.get('status'),str)or state['status']not in STATUSES:raise ValueError('invalid_status')
                if any(state.get(k)is not None and stamp(state[k])is None for k in('started_at','created_at','finished_at','completed_at','checked_at')if k in state):raise ValueError('invalid_timestamp')
                details={}
                if kind=='run':
                    model=state.get('model',{})
                    if not isinstance(model,dict)or not isinstance(state.get('metrics',{}),dict)or not isinstance(state.get('parameters',{}),dict):raise ValueError('invalid_nested_record')
                    cid=state.get('comparison_id')
                    details=dict(model_id=model.get('id')if model.get('id')in model_ids()else None,input_sha256=state.get('input_sha256')if re.fullmatch('[a-f0-9]{64}',str(state.get('input_sha256')))else None,comparison_id=cid if isinstance(cid,str)and re.fullmatch('[a-f0-9]{32}',cid)else None,metrics={k:number((state.get('metrics')or{}).get(k))for k in('total_seconds','loading_seconds','inference_seconds','peak_gpu_allocated_bytes')})
                elif kind=='comparison':
                    if not isinstance(state.get('run_ids'),list)or any(not isinstance(x,str)or not re.fullmatch('[a-f0-9]{32}',x)for x in state['run_ids']):raise ValueError('invalid_run_ids')
                    details=dict(run_ids=state['run_ids'])
                elif kind=='preparation':details={k:number(state.get(k))for k in('files_verified','total_bytes','downloaded_bytes')}
                elif kind=='task':details=dict(action=state.get('action')if state.get('action')in ACTIONS else'unknown',account=state.get('account')if state.get('account')in('A','B')else None)
                elif kind=='runtime_check':details=dict(cuda_available=state.get('cuda_available')if type(state.get('cuda_available'))is bool else None)
                records.append(self.event(kind,identifier,state,details,current=current))
            except (OSError,ValueError,KeyError,TypeError):
                event=self.event(kind,identifier,{},current=current);event['read_error']=True;records.append(event)
        records.sort(key=lambda r:(r['sort_at']is not None,r['sort_at']or'',r['kind'],r['id']),reverse=True)
        return records,issues

    def query(self,query):
        if set(query)-{'q','kind','status','limit','offset','snapshot'}or any(len(v)!=1 for v in query.values()):raise HistoryError('history_invalid_query')
        try:
            q=query.get('q',[''])[0].strip().casefold();kind=query.get('kind',[''])[0];status=query.get('status',[''])[0]
            limit=int(query.get('limit',['25'])[0]);offset=int(query.get('offset',['0'])[0]);snapshot=query.get('snapshot',[''])[0]
            if len(q)>300 or kind and kind not in KINDS or status and status not in STATUSES or limit not in(10,25,50)or not 0<=offset<=2**53-1:raise ValueError()
        except (ValueError,TypeError):raise HistoryError('history_invalid_query')from None
        filters=(q,kind,status)
        with self.lock:
            self.snapshots={k:v for k,v in self.snapshots.items()if v['expires']>time.monotonic()}
            if snapshot:
                value=self.snapshots.get(snapshot)
                if value is None:raise HistoryError('history_snapshot_expired')
                if value['filters']!=filters:raise HistoryError('history_snapshot_filter_mismatch')
            else:
                rows,issues=self._records()
                rows=[r for r in rows if(not kind or r['kind']==kind)and(not status or r['status']==status)and(not q or q in' '.join([r['id'],r['label'],r['kind'],str(r['details'].get('model_id')or''),str(r['details'].get('action')or'')]).casefold())]
                snapshot=secrets.token_hex(16)
                value=dict(rows=rows,issues=issues,filters=filters,expires=time.monotonic()+300,captured_at=datetime.now(timezone.utc).isoformat())
                if len(self.snapshots)>=16:self.snapshots.pop(next(iter(self.snapshots)))
                self.snapshots[snapshot]=value
            return dict(items=copy.deepcopy(value['rows'][offset:offset+limit]),total=len(value['rows']),snapshot=snapshot,captured_at=value['captured_at'],issues=value['issues'],offset=offset,limit=limit,has_more=offset+limit<len(value['rows']),sort='started_at_or_explicit_finish_desc_then_kind_id',snapshot_scope='fixed_until_refresh_or_5_minute_expiry')

    def detail(self,kind,identifier):
        if kind not in KINDS:raise HistoryError('history_not_found')
        rows,_=self._records()
        value=next((r for r in rows if r['kind']==kind and r['id']==identifier),None)
        if value is None:raise HistoryError('history_not_found')
        return value

    def performance(self,comparison_id,inference):
        try:pair=inference.comparison_get(comparison_id)
        except (OSError,KeyError,TypeError,AttributeError):raise HistoryError('performance_record_unavailable')from None
        if not isinstance(pair,dict)or not isinstance(pair.get('runs'),list)or len(pair['runs'])!=2:raise HistoryError('performance_record_unavailable')
        declared_ids=pair.get('run_ids')
        ids=[run.get('id')if isinstance(run,dict)else None for run in pair['runs']]
        model_pair=[(run.get('model')or{}).get('id')if isinstance(run,dict)and isinstance(run.get('model'),dict)else None for run in pair['runs']]
        pair_identity=isinstance(declared_ids,list)and ids==declared_ids and all(isinstance(i,str)and re.fullmatch('[a-f0-9]{32}',i)for i in ids)and len(set(ids))==2 and all(isinstance(i,str)for i in model_pair)and set(model_pair)==set(model_ids())
        rows=[];conditions=[]
        for side,run in zip(('A','B'),pair['runs']):
            if not isinstance(run,dict):run={}
            runid=run.get('id');valid_id=isinstance(runid,str)and re.fullmatch('[a-f0-9]{32}',runid)
            model=run.get('model')if isinstance(run.get('model'),dict)else{}
            parameters=run.get('parameters')if isinstance(run.get('parameters'),dict)else{}
            metrics=run.get('metrics')if isinstance(run.get('metrics'),dict)else{}
            proof=None;integrity='unconfirmed'
            try:
                if not valid_id:raise ValueError('invalid_run_identity')
                proof=read_record(self.home/'tts'/runid/'provenance.json',self.home)
                output=run.get('output')or{}
                if not isinstance(output,dict):raise ValueError('invalid_output')
                wav=regular(self.home/'tts'/runid/'output.wav',self.home)
                if run['status']=='succeeded'and wav.stat().st_size==output['bytes']and digest(wav)==output['sha256']:integrity='matched'
            except(OSError,ValueError,KeyError,TypeError):pass
            runtime_scope=None
            linked=bool(pair_identity and proof and valid_id and run.get('comparison_id')==comparison_id and run.get('comparison_side')==side and proof.get('comparison_side')==side and proof.get('run_id')==runid and re.fullmatch('[a-f0-9]{64}',str(run.get('input_sha256')))and proof.get('input_sha256')==run.get('input_sha256')and re.fullmatch('[a-f0-9]{64}',str(proof.get('manifest_sha256')))and proof.get('comparison_id')==comparison_id and model.get('id')in model_ids()and re.fullmatch('[a-f0-9]{40}',str(model.get('revision'))))
            try:
                declared=load_manifest(model['id'])
                source_input=read_record(self.home/'tts'/runid/'input.json',self.home)
                linked=bool(linked and model['revision']==declared['revision']and proof['manifest_sha256']==digest(manifest_path(model['id']))and source_input.get('parameters')==parameters and source_input.get('sha256')==run.get('input_sha256')and isinstance(source_input.get('text'),str)and hashlib.sha256(source_input['text'].encode()).hexdigest()==run.get('input_sha256'))
            except(OSError,ValueError,KeyError,TypeError):linked=False
            expected_code={'inference.py','tts_worker.py','models.py','preparation.py','server.py','external_process.py','runtime_bootstrap.py','runtime_paths.py','desktop.py','security.py','config.py','registry.py'}
            if linked and isinstance(proof.get('runtime_directory'),str)and Path(proof['runtime_directory']).is_absolute()and re.fullmatch('[a-f0-9]{64}',str(proof.get('runtime_lock_sha256')))and isinstance(proof.get('code_sha256'),dict)and set(proof['code_sha256'])==expected_code and all(re.fullmatch('[a-f0-9]{64}',str(h))for h in proof['code_sha256'].values()):
                runtime_scope=hashlib.sha256(json.dumps({k:proof.get(k)for k in('runtime_directory','runtime_lock_sha256','code_sha256')},sort_keys=True).encode()).hexdigest()
            from .inference import DEFAULTS
            valid_parameters=set(parameters)=={'language','speaker','batch_size','instruct','max_new_tokens','seed','sampling'}and type(parameters.get('seed'))is int and 0<=parameters['seed']<2**32 and type(parameters.get('batch_size'))is int and parameters['batch_size']==1 and isinstance(parameters.get('language'),str)and bool(parameters['language'])and isinstance(parameters.get('speaker'),str)and bool(parameters['speaker'])and (parameters.get('instruct')is None or isinstance(parameters.get('instruct'),str))and type(parameters.get('max_new_tokens'))is int and 0<parameters['max_new_tokens']<=4096
            sampling=parameters.get('sampling')
            valid_parameters=valid_parameters and isinstance(sampling,dict)and set(sampling)==set(DEFAULTS['sampling'])and all(type(sampling[k])is type(v)and(type(v)is bool or number(sampling[k])is not None)for k,v in DEFAULTS['sampling'].items())
            policy=pair.get('conditions')if isinstance(pair.get('conditions'),dict)else{}
            valid_policy=policy.get('cold_loading')is True and policy.get('cache_reuse')is False and type(policy.get('sample_count_per_model'))is int and policy['sample_count_per_model']==1 and valid_parameters and parameters==pair.get('parameters')and type(metrics.get('seed'))is int and metrics['seed']==parameters.get('seed')and proof is not None and proof.get('cold_loading')is True
            condition=dict(input_sha256=run.get('input_sha256')if re.fullmatch('[a-f0-9]{64}',str(run.get('input_sha256')))else None,parameters=parameters if valid_parameters else None,runtime_code_scope=runtime_scope,device=metrics.get('device')if isinstance(metrics.get('device'),str)and metrics['device'].strip()else None,dtype=metrics.get('dtype')if isinstance(metrics.get('dtype'),str)and metrics['dtype'].strip()else None,attention=metrics.get('attention')if isinstance(metrics.get('attention'),str)and metrics['attention'].strip()else None,cold_loading=True if metrics.get('cold_loading')is True else None,comparison_policy=True if valid_policy else None)
            conditions.append(condition)
            public_model={'id':model.get('id'),'name':load_manifest(model['id'])['name'],'revision':model.get('revision')if re.fullmatch('[a-f0-9]{40}',str(model.get('revision')))else None}if model.get('id')in model_ids()else None
            rows.append(dict(side=side,run_id=runid if valid_id else None,status=run.get('status')if isinstance(run.get('status'),str)and run['status']in STATUSES else'unknown',model=public_model,input_sha256=run.get('input_sha256')if re.fullmatch('[a-f0-9]{64}',str(run.get('input_sha256')))else None,seed=parameters.get('seed')if valid_parameters else None,measured_at=stamp(run.get('finished_at')),metrics={k:number(metrics.get(k))if run.get('status')=='succeeded'else None for k in('total_seconds','loading_seconds','inference_seconds','peak_gpu_allocated_bytes')},output_integrity=integrity,provenance_available=linked,manifest_sha256=proof.get('manifest_sha256')if linked else None,runtime_lock_sha256=proof.get('runtime_lock_sha256')if linked else None,recorded_conditions={k:condition[k]for k in('device','dtype','attention','cold_loading','runtime_code_scope')}|{'cache_reuse':policy.get('cache_reuse')if type(policy.get('cache_reuse'))is bool else None}))
        checks={k:conditions[0][k]is not None and conditions[0][k]==conditions[1][k]for k in conditions[0]}if len(conditions)==2 else{}
        comparable=bool(checks)and all(checks.values())and all(r['output_integrity']=='matched'and r['provenance_available']for r in rows)
        sample_count=1 if type(policy.get('sample_count_per_model'))is int and policy['sample_count_per_model']==1 else None
        safe_conditions={k:policy.get(k)if type(policy.get(k))is bool else None for k in('cold_loading','cache_reuse')}
        safe_conditions['sample_count_per_model']=sample_count
        safe_parameters=conditions[0]['parameters']if len(conditions)==2 and checks.get('parameters')else None
        return dict(comparison_id=comparison_id,status=pair.get('status')if isinstance(pair.get('status'),str)and pair['status']in STATUSES else'unknown',rows=rows,common_checks=checks,common_conditions_confirmed=comparable,sample_count_per_model=sample_count,conditions=safe_conditions,model_manifest_difference='intentional_comparison_subject',quality_winner=None,total_scope='includes_loading_integrity_and_process_overhead',memory_scope='pytorch_peak_allocated_not_total_vram',aggregation='none',parameters=safe_parameters)
