import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import io
from contextlib import redirect_stdout
from ai_manager.validation_contracts import (
    AXES, COUNTERS, ContractError, MAX_DOCUMENT_BYTES, canonical_bytes, document_sha,
    load_json, read_document, validate_plan, validate_ledger, validate_state, validate_transition,
)
from ai_manager.validation_profiles import catalog
from ai_manager.validation_prototype import example_bundle, validate_bundle, main


class ValidationContractsTests(unittest.TestCase):
    def setUp(self):
        self.bundle = example_bundle(1800000000)

    def reject(self, function, value, reason=None):
        with self.assertRaises(ContractError) as found:
            function(value)
        if reason:
            self.assertEqual(str(found.exception), reason)

    def test_actual_packaged_six_catalog(self):
        profiles, fingerprint = catalog()
        self.assertEqual(len(profiles), 6)
        self.assertEqual(fingerprint, '79bdc5cdf2c1f975ab352c5216a7f841bafc3b2c8ff794d29b4275e1ae73ca50')
        self.assertEqual(profiles['qwen-image-2.1']['required_bytes'], 33131601593)

    def test_fresh_example_no_model_test(self):
        result = validate_bundle(self.bundle)
        self.assertFalse(result['execution_authority'])
        self.assertFalse(result['model_test_performed'])
        self.assertNotEqual(self.bundle['plan']['batch_id'], example_bundle(1800000000)['plan']['batch_id'])

    def test_repeated_declaration_is_not_consumed_authority(self):
        self.assertEqual(validate_bundle(self.bundle),validate_bundle(self.bundle))
        self.assertFalse(validate_bundle(self.bundle)['execution_authority'])

    def test_cli_real_document_validation_and_safe_rejection(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'case.json';path.write_bytes(canonical_bytes(self.bundle))
            out=io.StringIO()
            with redirect_stdout(out):
                result=main(['validate','--root',folder,'--document','case.json'])
            self.assertEqual(result,0)
            self.assertEqual(json.loads(out.getvalue())['status'],'dry_run_contract_valid')
            path.write_bytes(b'{"private_input_marker":1}')
            out=io.StringIO()
            with redirect_stdout(out):result=main(['validate','--root',folder,'--document','case.json'])
            self.assertEqual(result,2)
            self.assertNotIn('private_input_marker',out.getvalue())
            self.assertNotIn(folder,out.getvalue())

    def test_reparse_rejected_without_os_symlink_privilege(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(Path,'lstat',return_value=SimpleNamespace(st_mode=0,st_file_attributes=0x400)):
                self.reject(lambda x:read_document(Path(folder),x),'case.json','document_reparse_rejected')

    def test_catalog_io_failure_is_safe_cli_result(self):
        for arguments in (['catalog'],['example','--now','1800000000']):
            out=io.StringIO()
            with patch.object(Path,'read_bytes',side_effect=OSError('PRIVATE_PATH_SENTINEL')):
                with redirect_stdout(out):result=main(arguments)
            self.assertEqual(result,2)
            self.assertEqual(json.loads(out.getvalue())['reason'],'catalog_read_failed')
            self.assertNotIn('PRIVATE_PATH_SENTINEL',out.getvalue())

    def test_hostile_root_rejected_before_io(self):
        for root in ('C:/m11-synthetic\x00root',123,None):
            self.reject(lambda x:read_document(x,'case.json'),root,'document_path_invalid')

    def test_modified_catalog_bytes_rejected_without_decode(self):
        with patch.object(Path,'read_bytes',return_value=b'\xffPRIVATE_PATH_SENTINEL'):
            self.reject(catalog_call,None,'catalog_manifest_changed')

    def test_json_entry_rejects_duplicates_numbers_encoding(self):
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1.0}', b'\xff'):
            with self.subTest(raw=raw): self.reject(load_json, raw)

    def test_complexity_bytes_depth_nodes(self):
        self.reject(load_json, b' '*(MAX_DOCUMENT_BYTES+1))
        self.reject(load_json, b'['*30+b'0'+b']'*30)
        self.reject(canonical_bytes, [0]*8193)
        self.reject(canonical_bytes, {'x':float('nan')})

    def test_unknown_bool_and_schema_rejected(self):
        for change in ('extra','bool','schema'):
            b=copy.deepcopy(self.bundle)
            if change=='extra': b['plan']['extra']=1
            if change=='bool': b['plan']['plan_version']=True
            if change=='schema': b['plan']['schema_version']=2
            self.reject(validate_bundle,b)

    def test_current_snapshot_is_independent_and_stale(self):
        b=self.bundle
        self.assertIsNot(b['current_snapshot'],b['plan']['snapshot'])
        b['current_snapshot']['code_sha256']='a'*64
        self.reject(validate_bundle,b,'snapshot_stale')

    def test_canonical_set_order_but_case_order_semantic(self):
        p=copy.deepcopy(self.bundle['plan']); original=validate_plan(p)
        p['snapshot']['candidates'].reverse()
        self.assertEqual(original.sha256,validate_plan(p).sha256)
        p['cases'][0],p['cases'][1]=p['cases'][1],p['cases'][0]
        self.assertNotEqual(original.sha256,validate_plan(p).sha256)

    def test_sealed_snapshot_not_mutated(self):
        p=self.bundle['plan']; frozen=validate_plan(p); before=frozen.sha256
        p['cases'].clear(); copy_out=frozen.as_dict(); copy_out['cases'].clear()
        self.assertEqual(before,frozen.sha256)
        self.assertEqual(len(frozen.as_dict()['cases']),6)

    def test_revision_catalog_and_candidate_duplicates(self):
        for change in ('revision','catalog','duplicate'):
            p=copy.deepcopy(self.bundle['plan'])
            if change=='revision': p['snapshot']['candidates'][0]['revision']='0'*40
            if change=='catalog': p['snapshot']['catalog_sha256']='0'*64
            if change=='duplicate': p['snapshot']['candidates'][1]['candidate_id']=p['snapshot']['candidates'][0]['candidate_id']
            self.reject(validate_plan,p)

    def test_cross_artifact_alias_both_directions(self):
        for field, oldfield in (('input','output'),('output','input')):
            p=copy.deepcopy(self.bundle['plan'])
            p['cases'][1][field][field+'_id']=p['cases'][0][oldfield][oldfield+'_id']
            self.reject(validate_plan,p,'artifact_duplicate')

    def test_future_hashes_are_unknown_not_fabricated(self):
        for path in ('input','output'):
            p=copy.deepcopy(self.bundle['plan']);p['cases'][0][path]['sha256']='a'*64
            self.reject(validate_plan,p)
        self.assertIsNone(self.bundle['plan']['cases'][2]['input']['lineage']['source_output_sha256'])

    def test_lineage_parent_case_output_and_rate(self):
        for field,value in (('source_case_id','f'*32),('source_output_id','f'*32),
                            ('source_output_sha256','a'*64),('sample_rate',24000),
                            ('max_duration_ms',30001),('channels',True)):
            p=copy.deepcopy(self.bundle['plan']);p['cases'][2]['input']['lineage'][field]=value
            self.reject(validate_plan,p)

    def test_dag_forward_cycle_and_cross_batch(self):
        for change in ('forward','crossbatch','oldsource'):
            p=copy.deepcopy(self.bundle['plan'])
            if change=='forward':p['cases'][0]['depends_on']=[p['cases'][2]['case_id']]
            if change=='crossbatch':p['cases'][2]['input']['batch_id']='f'*32
            if change=='oldsource':p['cases'][2]['input']['source']='previous_run_output'
            self.reject(validate_plan,p)

    def test_designated_current_requires_known_hash(self):
        p=copy.deepcopy(self.bundle['plan']);c=p['cases'][2]
        c['depends_on']=[];c['input'].update(source='designated_current',recipe_id='m11-designated-wav16k-v1',lineage=None)
        self.reject(validate_plan,p)
        c['input']['sha256']='a'*64
        validate_plan(p)

    def test_future_execution_capabilities_denied(self):
        for field,value in (('action','infer'),('mode','execute')):
            b=copy.deepcopy(self.bundle);b['approval'][field]=value
            self.reject(validate_bundle,b)
        for key in ('max_transfer_bytes','max_installations','max_worker_runs'):
            p=copy.deepcopy(self.bundle['plan']);p['limits'][key]=1
            self.reject(validate_plan,p)

    def test_expiry_and_stale_snapshot_or_plan(self):
        for change in ('expiry','future','snapshot','plan','approval_limit'):
            b=copy.deepcopy(self.bundle)
            if change=='expiry':b['now']+=600
            if change=='future':b['now']-=1
            if change=='snapshot':b['current_snapshot']['code_sha256']='a'*64
            if change=='plan':b['plan']['plan_version']=2
            if change=='approval_limit':b['approval']['limits']['max_read_bytes']-=1
            self.reject(validate_bundle,b)

    def test_cumulative_ledger_no_reset_unknown_or_rollback(self):
        p=validate_plan(self.bundle['plan']);old=self.bundle['ledger']
        new=copy.deepcopy(old);new.update(sequence=1,previous_sha256=document_sha(old),observed_at=old['observed_at']+1)
        new['consumed']['read_bytes']=12
        validate_ledger(new,p,old)
        self.reject(lambda x:validate_ledger(x,p),new,'ledger_history_required')
        unknown=copy.deepcopy(new);unknown['known']=False
        self.reject(lambda x:validate_ledger(x,p,old),unknown,'ledger_unknown')
        later=copy.deepcopy(new);later.update(sequence=2,previous_sha256=document_sha(new));later['consumed']['read_bytes']=0
        self.reject(lambda x:validate_ledger(x,p,new),later,'ledger_rollback')
        new['consumed']['worker_runs']=1
        self.reject(lambda x:validate_ledger(x,p,old),new,'budget_exceeded')

    def test_read_document_no_escape_or_nonregular(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'safe.json').write_bytes(b'{"a":1}')
            self.assertEqual(read_document(root,'safe.json'),{'a':1})
            for relative in ('../safe.json','/safe.json','C:/safe.json','x\\safe.json','safe.json:stream','.'):
                self.reject(lambda x:read_document(root,x),relative)
            self.reject(lambda x:read_document(root,x),'missing.json')
            self.reject(lambda x:read_document(root,x),'subdirectory')

    def test_read_document_symlink_if_supported(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'safe.json').write_bytes(b'{}')
            try:(root/'link.json').symlink_to(root/'safe.json')
            except OSError:self.skipTest('OS does not permit unprivileged symlinks')
            self.reject(lambda x:read_document(root,x),'link.json')

    def test_state_synthetic_only_and_terminal_immutable(self):
        state=dict(schema_version=1,batch_id='a'*32,case_id='b'*32,attempt=1,observed_at=100,
            axes={key:values[0] for key,values in AXES.items()},quality='not_assessed',evidence_kind='synthetic_contract')
        validate_state(state)
        terminal=copy.deepcopy(state);terminal['axes']['execution']='cancelled'
        validate_transition(state,terminal)
        changed=copy.deepcopy(terminal);changed['observed_at']=101
        self.reject(lambda x:validate_transition(terminal,x),changed,'terminal_state_immutable')
        bad=copy.deepcopy(state);bad['axes']['execution']='succeeded'
        self.reject(validate_state,bad,'state_preflight_inconsistent')
        bad=copy.deepcopy(state);bad['evidence_kind']='real_inference'
        self.reject(validate_state,bad)


def catalog_call(_):return catalog()


if __name__=='__main__':unittest.main()
