"""M11 declaration contracts only. No scanning, preparation, or worker dispatch."""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat

MAX_DOCUMENT_BYTES = 262144
MAX_DEPTH = 24
MAX_NODES = 8192
ZERO_SHA = '0' * 64


class ContractError(ValueError):
    """Stable error code without input values or private paths."""


def fail(code):
    raise ContractError(code)


def object_fields(value, fields):
    if type(value) is not dict or set(value) != set(fields):
        fail('object_fields_invalid')
    return value


def integer(value, low=0, high=2**53-1):
    if type(value) is not int or not low <= value <= high:
        fail('integer_invalid')
    return value


def identifier(value):
    if type(value) is not str or not re.fullmatch('[a-f0-9]{32}', value):
        fail('identifier_invalid')
    return value


def digest_value(value):
    if type(value) is not str or not re.fullmatch('[a-f0-9]{64}', value):
        fail('digest_invalid')
    return value


def choice(value, values):
    if type(value) is not str or value not in values:
        fail('enum_invalid')
    return value


def sequence(value, maximum=6, minimum=0):
    if type(value) is not list or not minimum <= len(value) <= maximum:
        fail('sequence_invalid')
    return value


def _tree(value, depth=0, counter=None):
    counter = [0] if counter is None else counter
    counter[0] += 1
    if depth > MAX_DEPTH or counter[0] > MAX_NODES:
        fail('document_complexity_limit')
    if value is None or type(value) is bool:
        return
    if type(value) is int:
        integer(value, -(2**53-1))
    elif type(value) is str:
        if len(value) > 2048 or any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in value):
            fail('string_invalid')
    elif type(value) is list:
        for item in value:
            _tree(item, depth+1, counter)
    elif type(value) is dict:
        for key, item in value.items():
            if type(key) is not str or len(key) > 128:
                fail('object_key_invalid')
            _tree(key, depth+1, counter)
            _tree(item, depth+1, counter)
    else:
        # Even finite floats are outside the v1 integer-only wire contract.
        fail('json_type_invalid')


def canonical_bytes(value):
    _tree(value)
    data = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')
    if len(data) > MAX_DOCUMENT_BYTES:
        fail('document_size_limit')
    return data


def document_sha(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def load_json(data):
    if type(data) is not bytes or len(data) > MAX_DOCUMENT_BYTES:
        fail('document_size_limit')
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                fail('duplicate_json_key')
            out[key] = value
        return out
    def bad_number(_):
        fail('json_number_invalid')
    try:
        value = json.loads(data.decode('utf-8'), object_pairs_hook=pairs,
                           parse_float=bad_number, parse_constant=bad_number)
        _tree(value)
        return value
    except ContractError:
        raise
    except (ValueError, UnicodeError, RecursionError):
        fail('json_invalid')


def read_document(root, relative):
    """Read one bounded regular JSON file, never a model or recursive tree."""
    if not isinstance(root, (str, Path)) or any(ord(c)<32 for c in str(root)):
        fail('document_path_invalid')
    root = Path(root)
    if not root.is_absolute() or '..' in root.parts or type(relative) is not str:
        fail('document_path_invalid')
    parts = relative.split('/')
    if not parts or any(not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', x) or x in ('.', '..') for x in parts):
        fail('document_path_invalid')
    target = root.joinpath(*parts)
    def inspect():
        for item in (*reversed(target.parents), target):
            info = item.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                fail('document_reparse_rejected')
        info = target.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_DOCUMENT_BYTES:
            fail('document_file_invalid')
        return info
    try:
        before = inspect()
        with os.fdopen(os.open(target, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)), 'rb') as stream:
            opened = os.fstat(stream.fileno())
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                fail('document_changed')
            inspect()
            data = stream.read(MAX_DOCUMENT_BYTES+1)
            after = os.fstat(stream.fileno())
        current = inspect()
        sig = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
        if sig(before) != sig(after) or sig(after) != sig(current):
            fail('document_changed')
        return load_json(data)
    except ContractError:
        raise
    except (OSError, ValueError):
        fail('document_read_failed')


@dataclass(frozen=True)
class FrozenDocument:
    """Canonical immutable bytes; returned dicts cannot mutate the sealed value."""
    data: bytes

    @property
    def sha256(self):
        return hashlib.sha256(self.data).hexdigest()

    def as_dict(self):
        return load_json(self.data)


def seal(value):
    return FrozenDocument(canonical_bytes(value))


LIMIT_FIELDS = ('max_wall_seconds', 'max_read_bytes', 'max_transfer_bytes', 'max_installations', 'max_worker_runs')
COUNTERS = ('wall_seconds', 'read_bytes', 'transfer_bytes', 'installations', 'worker_runs')


def limits(value):
    object_fields(value, LIMIT_FIELDS)
    integer(value['max_wall_seconds'], 1, 86400)
    integer(value['max_read_bytes'], 0, MAX_DOCUMENT_BYTES*8)
    for field in LIMIT_FIELDS[2:]:
        integer(value[field], 0, 0)  # M11 can never authorize these effects.
    return dict(value)


def validate_snapshot(value):
    from .validation_profiles import catalog
    profiles, catalog_sha = catalog()
    object_fields(value, ('schema_version','snapshot_id','registry_generation','source_proof_sha256',
                          'code_sha256','runtime_lock_sha256','catalog_sha256','candidates'))
    integer(value['schema_version'], 1, 1)
    identifier(value['snapshot_id']); identifier(value['registry_generation'])
    for key in ('source_proof_sha256','code_sha256','runtime_lock_sha256','catalog_sha256'):
        digest_value(value[key])
    if value['catalog_sha256'] != catalog_sha:
        fail('catalog_stale')
    candidates = sequence(value['candidates'], minimum=1)
    ids = set()
    for candidate in candidates:
        object_fields(candidate, ('candidate_id','profile_id','revision','manifest_sha256'))
        key = identifier(candidate['candidate_id'])
        if key in ids: fail('candidate_duplicate')
        ids.add(key)
        profile = profiles.get(candidate['profile_id']) if type(candidate['profile_id']) is str else None
        if profile is None: fail('profile_unsupported')
        if candidate['revision'] != profile['revision'] or candidate['manifest_sha256'] != profile['manifest_sha256']:
            fail('profile_revision_mismatch')
    normalized = dict(value, candidates=sorted(candidates, key=lambda x:x['candidate_id']))
    return seal(normalized)


def validate_plan(value):
    from .validation_profiles import catalog
    profiles, _ = catalog()
    object_fields(value, ('schema_version','batch_id','plan_version','mode','action','created_at','expires_at',
                          'snapshot','limits','cases'))
    integer(value['schema_version'], 1, 1); batch = identifier(value['batch_id'])
    integer(value['plan_version'], 1, 1000000)
    choice(value['mode'], ('dry_run',)); choice(value['action'], ('validate_plan',))
    created = integer(value['created_at'], 0, 2**32-1)
    expiry = integer(value['expires_at'], created+1, created+86400)
    policy = limits(value['limits'])
    if expiry-created > policy['max_wall_seconds']: fail('expiry_exceeds_limit')
    snapshot = validate_snapshot(value['snapshot']).as_dict()
    candidates = {x['candidate_id']:x for x in snapshot['candidates']}
    cases = sequence(value['cases'], minimum=1)
    seen, used_inputs, used_outputs, used_candidates = {}, set(), set(), set()
    normalized = []
    for case in cases:
        object_fields(case, ('case_id','candidate_id','profile_id','depends_on','input','output'))
        cid = identifier(case['case_id']); candidate = identifier(case['candidate_id'])
        if cid in seen or candidate in used_candidates: fail('case_duplicate')
        if candidate not in candidates or candidates[candidate]['profile_id'] != case['profile_id']:
            fail('case_candidate_mismatch')
        profile = profiles[case['profile_id']]
        deps = sequence(case['depends_on'])
        for dep in deps: identifier(dep)
        if len(set(deps)) != len(deps) or any(x not in seen for x in deps): fail('dependency_invalid')
        inp, out = case['input'], case['output']
        object_fields(inp, ('input_id','batch_id','kind','source','recipe_id','sha256','lineage'))
        object_fields(out, ('output_id','kind','sha256'))
        iid, oid = identifier(inp['input_id']), identifier(out['output_id'])
        if iid in used_inputs | used_outputs or oid in used_inputs | used_outputs or iid == oid:
            fail('artifact_duplicate')
        identifier(inp['batch_id'])
        # These are proposals for future artifacts, never fabricated known hashes.
        if out['sha256'] is not None: fail('future_output_hash_forbidden')
        if inp['source'] == 'designated_current':
            digest_value(inp['sha256'])
        elif inp['sha256'] is not None:
            fail('future_input_hash_forbidden')
        if inp['batch_id'] != batch: fail('input_batch_mismatch')
        if inp['kind'] != profile['input_kind'] or out['kind'] != profile['output_kind']:
            fail('artifact_kind_mismatch')
        if case['profile_id'] == 'whisper-large-v3-turbo':
            choice(inp['source'], ('same_batch_output','designated_current'))
            if inp['source'] == 'same_batch_output':
                line = object_fields(inp['lineage'], ('source_case_id','source_output_id','source_output_sha256',
                                                      'transform','source_rate','sample_rate','channels','sample_width','max_duration_ms'))
                parent = identifier(line['source_case_id'])
                if deps != [parent] or parent not in seen: fail('lineage_dependency_invalid')
                source = seen[parent]
                if not source['profile_id'].startswith('qwen3-tts-') or source['output']['kind'] != 'wav':
                    fail('lineage_source_invalid')
                if line['source_output_id'] != source['output']['output_id'] or line['source_output_sha256'] != source['output']['sha256']:
                    fail('lineage_digest_mismatch')
                choice(line['transform'], ('pcm24k_to_pcm16k_mono-v1',))
                integer(line['source_rate'],24000,24000); integer(line['sample_rate'],16000,16000)
                integer(line['channels'],1,1); integer(line['sample_width'],2,2); integer(line['max_duration_ms'],1,30000)
                if inp['recipe_id'] != 'm11-derived-wav16k-v1': fail('recipe_invalid')
            elif deps or inp['lineage'] is not None or inp['recipe_id'] != 'm11-designated-wav16k-v1':
                fail('lineage_invalid')
        elif inp['source'] != 'fresh_generated' or inp['recipe_id'] != profile['recipe_id'] or inp['lineage'] is not None or deps:
            fail('fresh_input_required')
        current = dict(case, depends_on=sorted(deps))
        seen[cid] = current; used_inputs.add(iid); used_outputs.add(oid); used_candidates.add(candidate)
        normalized.append(current)
    if set(candidates) != used_candidates: fail('unplanned_candidate')
    return seal(dict(value, snapshot=snapshot, limits=policy, cases=normalized))


def validate_ledger(value, plan, previous=None):
    object_fields(value, ('schema_version','batch_id','plan_sha256','sequence','previous_sha256','known','observed_at','consumed'))
    integer(value['schema_version'],1,1); identifier(value['batch_id']); digest_value(value['plan_sha256'])
    n = integer(value['sequence'],0,1000000); digest_value(value['previous_sha256'])
    if type(value['known']) is not bool or not value['known']: fail('ledger_unknown')
    integer(value['observed_at'],0,2**32-1)
    consumed = object_fields(value['consumed'],COUNTERS)
    for key in COUNTERS: integer(consumed[key])
    p = plan.as_dict()
    if value['batch_id'] != p['batch_id'] or value['plan_sha256'] != plan.sha256: fail('ledger_scope_mismatch')
    if previous is None:
        if n != 0 or value['previous_sha256'] != ZERO_SHA or any(consumed.values()): fail('ledger_history_required')
    else:
        old = object_fields(previous, ('schema_version','batch_id','plan_sha256','sequence','previous_sha256','known','observed_at','consumed'))
        # The caller supplies its trusted last ledger; this module has no durable store.
        integer(old['schema_version'],1,1); integer(old['sequence'],0,1000000)
        integer(old['observed_at'],0,2**32-1)
        object_fields(old['consumed'],COUNTERS)
        for key in COUNTERS: integer(old['consumed'][key])
        if old['known'] is not True or old['batch_id'] != p['batch_id'] or old['plan_sha256'] != plan.sha256:
            fail('ledger_scope_mismatch')
        if n != old['sequence']+1 or value['previous_sha256'] != document_sha(old): fail('ledger_chain_invalid')
        if value['observed_at'] < old['observed_at'] or any(consumed[k] < old['consumed'][k] for k in COUNTERS):
            fail('ledger_rollback')
    if any(consumed[k] > p['limits'][limit] for k,limit in zip(COUNTERS,LIMIT_FIELDS)):
        fail('budget_exceeded')
    return seal(value)


def check_approval(plan_value, approval, current_snapshot, ledger, now, previous_ledger=None):
    plan = validate_plan(plan_value); p = plan.as_dict()
    object_fields(approval, ('schema_version','approval_id','actor','mode','action','batch_id','plan_version',
                             'plan_sha256','snapshot_sha256','catalog_sha256','issued_at','expires_at','limits'))
    integer(approval['schema_version'],1,1); identifier(approval['approval_id'])
    if type(approval['actor']) is not str or not re.fullmatch('[A-Za-z0-9_-]{1,64}', approval['actor']): fail('actor_label_invalid')
    choice(approval['mode'],('dry_run',)); choice(approval['action'],('validate_plan',))
    identifier(approval['batch_id']); integer(approval['plan_version'],1,1000000)
    for key in ('plan_sha256','snapshot_sha256','catalog_sha256'): digest_value(approval[key])
    integer(now,0,2**32-1); issued = integer(approval['issued_at'],p['created_at'],p['expires_at']-1)
    expiry = integer(approval['expires_at'],issued+1,p['expires_at'])
    if now < issued or now >= expiry or now >= p['expires_at']: fail('approval_expired_or_future')
    actual = validate_snapshot(current_snapshot)
    if actual.sha256 != document_sha(p['snapshot']): fail('snapshot_stale')
    if (approval['batch_id'] != p['batch_id'] or approval['plan_version'] != p['plan_version']
            or approval['plan_sha256'] != plan.sha256 or approval['snapshot_sha256'] != actual.sha256
            or approval['catalog_sha256'] != p['snapshot']['catalog_sha256']): fail('approval_stale')
    if limits(approval['limits']) != p['limits']: fail('approval_limits_mismatch')
    record = validate_ledger(ledger,plan,previous_ledger).as_dict()
    if not p['created_at'] <= record['observed_at'] <= now: fail('ledger_time_invalid')
    if max(now-p['created_at'],record['consumed']['wall_seconds']) >= p['limits']['max_wall_seconds']:
        fail('budget_exceeded')
    return {'status':'dry_run_contract_valid','execution_authority':False,'model_test_performed':False,
            'plan_sha256':plan.sha256,'snapshot_sha256':actual.sha256,'quality':'not_assessed'}


AXES = {
    'identity':('unknown','ambiguous','unsupported','profile_match','revision_mismatch'),
    'artifact':('uninspected','incomplete','hash_mismatch','matched'),
    'environment':('uninspected','unprepared','ready'),
    'resource':('uninspected','blocked','ready'),
    'execution':('not_started','awaiting_approval','deferred','queued','running','validating','succeeded',
                 'run_failed','cancelled','timed_out','interrupted'),
    'output':('uninspected','invalid','validated'),
}
TRANSITIONS = {
    'not_started':{'awaiting_approval','deferred','queued','cancelled'},
    'awaiting_approval':{'queued','deferred','cancelled'},
    'deferred':set(), 'queued':{'running','cancelled','timed_out','interrupted','run_failed'},
    'running':{'validating','run_failed','cancelled','timed_out','interrupted'},
    'validating':{'succeeded','run_failed','cancelled','timed_out','interrupted'},
    'succeeded':set(),'run_failed':set(),'cancelled':set(),'timed_out':set(),'interrupted':set(),
}


def validate_state(value):
    object_fields(value, ('schema_version','batch_id','case_id','attempt','observed_at','axes','quality','evidence_kind'))
    integer(value['schema_version'],1,1); identifier(value['batch_id']); identifier(value['case_id'])
    integer(value['attempt'],1,1000000); integer(value['observed_at'],0,2**32-1)
    choice(value['quality'],('not_assessed',)); choice(value['evidence_kind'],('synthetic_contract',))
    axes=object_fields(value['axes'],AXES)
    for key, values in AXES.items(): choice(axes[key],values)
    if axes['execution'] in ('running','validating','succeeded'):
        if any(axes[k] != required for k,required in (('identity','profile_match'),('artifact','matched'),('environment','ready'),('resource','ready'))):
            fail('state_preflight_inconsistent')
    if axes['execution']=='succeeded' and axes['output']!='validated': fail('state_output_unvalidated')
    if axes['output']=='validated' and axes['execution']!='succeeded': fail('state_output_inconsistent')
    return seal(value)


def validate_transition(before, after):
    old,new=validate_state(before).as_dict(),validate_state(after).as_dict()
    if any(old[k]!=new[k] for k in ('batch_id','case_id','attempt')): fail('transition_scope_mismatch')
    if new['observed_at']<old['observed_at']: fail('transition_time_rollback')
    source,target=old['axes']['execution'],new['axes']['execution']
    if source!=target and target not in TRANSITIONS[source]: fail('transition_invalid')
    if not TRANSITIONS[source] and old!=new: fail('terminal_state_immutable')
    return seal(new)
