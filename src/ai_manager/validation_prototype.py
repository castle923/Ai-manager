"""M11 stdlib-only declaration CLI. No scanner, installer, or dispatcher."""
import argparse
import copy
import json
import sys
import uuid
from .validation_contracts import (
    COUNTERS, ContractError, ZERO_SHA, check_approval, document_sha, integer,
    object_fields, read_document, validate_plan, validate_state, validate_transition,
)
from .validation_profiles import catalog


def example_bundle(now):
    """Fresh synthetic declarations only; no model or generated media is read."""
    integer(now, 0, 2**32-1-600)
    uid = lambda: uuid.uuid4().hex
    profiles, fingerprint = catalog()
    batch = uid()
    snapshot = dict(schema_version=1, snapshot_id=uid(), registry_generation=uid(),
                    source_proof_sha256=ZERO_SHA, code_sha256=ZERO_SHA,
                    runtime_lock_sha256=ZERO_SHA, catalog_sha256=fingerprint, candidates=[])
    plan = dict(schema_version=1, batch_id=batch, plan_version=1, mode='dry_run',
                action='validate_plan', created_at=now, expires_at=now+600,
                snapshot=snapshot, limits=dict(max_wall_seconds=600, max_read_bytes=2097152,
                max_transfer_bytes=0, max_installations=0, max_worker_runs=0), cases=[])
    parent = None
    for key, profile in profiles.items():
        candidate = uid()
        snapshot['candidates'].append(dict(candidate_id=candidate, profile_id=key,
            revision=profile['revision'], manifest_sha256=profile['manifest_sha256']))
        inp = dict(input_id=uid(), batch_id=batch, kind=profile['input_kind'],
                   source='fresh_generated', recipe_id=profile['recipe_id'], sha256=None, lineage=None)
        case = dict(case_id=uid(), candidate_id=candidate, profile_id=key, depends_on=[],
                    input=inp, output=dict(output_id=uid(), kind=profile['output_kind'], sha256=None))
        if key == 'whisper-large-v3-turbo':
            case['depends_on'] = [parent['case_id']]
            inp.update(source='same_batch_output', lineage=dict(source_case_id=parent['case_id'],
                source_output_id=parent['output']['output_id'], source_output_sha256=None,
                transform='pcm24k_to_pcm16k_mono-v1', source_rate=24000, sample_rate=16000,
                channels=1, sample_width=2, max_duration_ms=30000))
        plan['cases'].append(case)
        if parent is None:
            parent = case
    frozen = validate_plan(plan)
    normalized = frozen.as_dict()
    approval = dict(schema_version=1, approval_id=uid(), actor='simulation_only',
        mode='dry_run', action='validate_plan', batch_id=batch, plan_version=1,
        plan_sha256=frozen.sha256, snapshot_sha256=document_sha(normalized['snapshot']),
        catalog_sha256=fingerprint, issued_at=now, expires_at=now+600, limits=copy.deepcopy(plan['limits']))
    ledger = dict(schema_version=1, batch_id=batch, plan_sha256=frozen.sha256, sequence=0,
        previous_sha256=ZERO_SHA, known=True, observed_at=now, consumed={key:0 for key in COUNTERS})
    return dict(plan=normalized, approval=approval, current_snapshot=copy.deepcopy(normalized['snapshot']),
                ledger=ledger, now=now, previous_ledger=None)


def validate_bundle(value):
    object_fields(value, ('plan','approval','current_snapshot','ledger','now','previous_ledger'))
    return check_approval(value['plan'], value['approval'], value['current_snapshot'],
                          value['ledger'], value['now'], value['previous_ledger'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('catalog')
    example = sub.add_parser('example')
    example.add_argument('--now', required=True, type=int, help='Explicit synthetic UTC epoch seconds')
    for command in ('validate', 'state', 'transition'):
        entry = sub.add_parser(command)
        entry.add_argument('--root', required=True)
        entry.add_argument('--document', required=True, help='Bounded relative JSON filename')
    args = parser.parse_args(argv)
    try:
        if args.command == 'catalog':
            profiles, fingerprint = catalog()
            result = dict(schema_version=1, catalog_sha256=fingerprint, profiles=profiles,
                          execution_authority=False, model_test_performed=False)
        elif args.command == 'example':
            result = example_bundle(args.now)
        else:
            value = read_document(args.root, args.document)
            if args.command == 'validate':
                result = validate_bundle(value)
            elif args.command == 'state':
                result = dict(status='state_contract_valid', declaration=validate_state(value).as_dict(),
                              execution_authority=False, model_test_performed=False)
            else:
                object_fields(value, ('before','after'))
                result = dict(status='transition_contract_valid', declaration=validate_transition(
                    value['before'],value['after']).as_dict(), execution_authority=False, model_test_performed=False)
        print(json.dumps(result, ensure_ascii=True, sort_keys=True, allow_nan=False))
        return 0
    except ContractError as exc:
        print(json.dumps(dict(status='contract_rejected', reason=str(exc),
                              execution_authority=False, model_test_performed=False)))
        return 2


if __name__ == '__main__':
    sys.exit(main())
