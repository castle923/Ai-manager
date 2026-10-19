"""Fresh metadata fixtures; no model bytes, Drive access, or inference."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ai_manager.candidate_recommendations import _profiles, explain
from ai_manager.dashboard import Dashboard, family
from ai_manager.inventory import kind


def profile(identifier):
    return next(p for p in _profiles() if p['model_id']==identifier)


def root_files(p):
    return [f for f in p['files'] if '/' not in f['path'] and (Path(f['path']).suffix in {'.safetensors','.bin','.pt','.gguf','.pth'} or f['path'] in {'config.json','model_index.json','preprocessor_config.json','processor_config.json'})]


def seed(dashboard, groups, status='complete', account='A'):
    with dashboard.inventory.connect() as db:
        db.execute("INSERT INTO scans(scan_id,account,settings_version,settings_json,started_at,status,pid,files_count) VALUES(?,?,1,'{}','2026-10-19',?,0,?)",('fresh-'+account,account,status,sum(len(g['files']) for g in groups)))
        counter=0
        for index,group in enumerate(groups):
            for f in group['files']:
                counter+=1;metadata=dict(name=f['path'],size=str(f['size']),parents=['fresh-parent-'+str(index)])
                db.execute('INSERT INTO files VALUES(?,?,?,?,?,?)',('fresh-'+account,str(counter),'ROOT','ROOT/'+group['path']+'/'+f['path'],kind(f['path']) or 'weight_candidate',json.dumps(metadata)))


class RecommendationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.home=Path(self.temp.name);self.dashboard=Dashboard(self.home)

    def tearDown(self):self.temp.cleanup()

    def group(self,identifier,**changes):
        p=profile(identifier)
        return dict(path=p['name'].rsplit('/',1)[-1],files=root_files(p))|changes

    def test_default_requires_purpose_and_never_invents_performance(self):
        seed(self.dashboard,[self.group('qwen3-tts-0.6b-customvoice')])
        result=self.dashboard.query({})
        self.assertEqual(result['recommendation']['recommended'],0)
        r=result['rows'][0]['recommendation'];self.assertIsNone(r['rank']);self.assertEqual(r['quality'],'unassessed');self.assertEqual(r['execution'],'unverified')
        self.assertIn('choose_purpose',r['reason_codes']);self.assertNotIn('score',r)

    def test_complete_metadata_groups_rank_by_name_not_parameter_size(self):
        seed(self.dashboard,[self.group('qwen3-tts-1.7b-customvoice'),self.group('qwen3-tts-0.6b-customvoice')])
        result=self.dashboard.query({'purpose':['tts']})
        self.assertEqual(result['recommendation']['recommended'],2)
        self.assertEqual([r['recommendation']['rank'] for r in result['rows']],[1,2])
        self.assertIn('0.6B',result['rows'][0]['name'])
        self.assertTrue(all(r['recommendation']['identity']=='unverified' for r in result['rows']))

    def test_tapir_single_checkpoint_does_not_require_invented_config(self):
        seed(self.dashboard,[self.group('tapir')])
        result=self.dashboard.query({'purpose':['tracking']})
        self.assertEqual(result['recommendation']['recommended'],1)
        self.assertNotIn('config_not_observed',result['rows'][0]['recommendation']['reason_codes'])

    def test_distributed_image_is_related_and_explicitly_deferred_not_absent(self):
        seed(self.dashboard,[self.group('qwen-image-2.1')])
        result=self.dashboard.query({'purpose':['image']})
        self.assertEqual(result['recommendation']['recommended'],0);self.assertEqual(result['recommendation']['related'],1)
        self.assertIn('distributed_weights_unobserved',result['rows'][0]['recommendation']['reason_codes'])
        self.assertIn('편집',str(result['recommendation']['limitations']))
        self.assertEqual(kind('model_index.json'),'model_component_candidate')

    def test_partial_and_missing_metadata_never_receive_rank(self):
        seed(self.dashboard,[self.group('qwen3-tts-0.6b-customvoice')],status='partial')
        result=self.dashboard.query({'purpose':['tts']})['rows'][0]['recommendation']
        self.assertIsNone(result['rank']);self.assertIn('incomplete_scan',result['reason_codes'])
        row=self.dashboard.snapshot()['models'][0];row['scan_status']='complete';row['files']=[f for f in row['files'] if f['name']!='config.json']
        self.assertIn('config_not_observed',explain(row,'tts')['reason_codes'])

    def test_components_subfolders_duplicate_names_and_shards_are_not_models(self):
        p=profile('qwen3-tts-0.6b-customvoice');group=self.group(p['model_id'])
        seed(self.dashboard,[group])
        row=self.dashboard.snapshot()['models'][0]
        self.assertFalse(explain(row|{'name':'speech_tokenizer'},'tts')['eligible'])
        self.assertIn('not_model_root',explain(row|{'name':'speech_tokenizer'},'tts')['reason_codes'])
        duplicate=explain(row|{'files':row['files']+[row['files'][0]]},'tts')
        self.assertFalse(duplicate['eligible']);self.assertIn('duplicate_names',duplicate['reason_codes'])
        self.assertIn('shards_missing',explain(row|{'observations':{'shards_missing':1}},'tts')['reason_codes'])

    def test_profile_names_are_exact_segments_and_multiple_names_are_ambiguous(self):
        p=profile('qwen3-tts-0.6b-customvoice');g=self.group(p['model_id'])
        seed(self.dashboard,[g])
        row=self.dashboard.snapshot()['models'][0]
        r=explain(row|{'path':row['path']+'-untrusted-suffix','name':row['name']+'-untrusted-suffix'},'tts')
        self.assertFalse(r['eligible']);self.assertEqual(r['profile_name_candidates'],[])
        r=explain(row|{'path':row['path']+'/whisper-large-v3-turbo'},'tts')
        self.assertFalse(r['eligible']);self.assertIn('ambiguous_profile',r['reason_codes'])

    def test_filters_global_rank_and_pagination_keep_the_same_policy(self):
        seed(self.dashboard,[self.group('qwen3-tts-0.6b-customvoice',path=f'{i:02}/Qwen3-TTS-12Hz-0.6B-CustomVoice') for i in range(27)])
        first=self.dashboard.query({'purpose':['tts'],'limit':['24']});second=self.dashboard.query({'purpose':['tts'],'limit':['24'],'page':['2']})
        self.assertEqual([r['recommendation']['rank'] for r in second['rows']],[25,26,27])
        self.assertEqual(first['recommendation']['recommended'],27)
        for filters in ({'account':['B']},{'family':['이미지 생성']},{'q':['no-such-new-input']},{'kind':['distribution_document_candidate']}):
            result=self.dashboard.query({'purpose':['tts']}|filters)
            self.assertEqual(result['rows'],[]);self.assertEqual(result['recommendation']['recommended'],0)

    def test_all_sort_modes_preserve_rank_and_files_have_relevance_not_model_numbers(self):
        seed(self.dashboard,[self.group('qwen3-tts-0.6b-customvoice'),self.group('whisper-large-v3-turbo')])
        for view in ('models','files'):
            for sort in ('recommendation','name','size','modified'):
                result=self.dashboard.query({'purpose':['tts'],'view':[view],'sort':[sort]})
                self.assertEqual(result['recommendation']['purpose'],'tts')
                if view=='files':self.assertTrue(all(r['recommendation']['rank'] is None for r in result['rows']))
        row=self.dashboard.query({'purpose':['tts']})['rows'][0]
        detail=self.dashboard.detail(row['id'],row['scan_id'],'tts')
        self.assertTrue(detail['recommendation']['eligible']);self.assertIsNone(detail['recommendation']['rank'])

    def test_unsupported_and_wrong_task_get_no_rank_or_support_claim(self):
        seed(self.dashboard,[self.group('whisper-large-v3-turbo'),dict(path='Kokoro',files=[dict(path='model.safetensors',size=123)])])
        result=self.dashboard.query({'purpose':['tts']})
        self.assertEqual(result['recommendation']['recommended'],0)
        self.assertTrue(all(r['recommendation']['rank'] is None for r in result['rows']))

    def test_family_uses_nearest_specific_hint_not_tts_archive_substring(self):
        self.assertEqual(family('TTS-archive/whisper-large-v3-turbo/model.safetensors'),'음성 인식')
        self.assertEqual(family('TTS-archive/Qwen-Image-2.1/transformer/model.safetensors'),'이미지 생성')
        self.assertEqual(family('ROOT/BootsTAPIR/checkpoint.pt'),'영상 추적')
        self.assertEqual(family('ROOT/notts/model.bin'),'미분류')

    def test_read_only_query_does_not_recover_or_write_existing_scan(self):
        seed(self.dashboard,[self.group('qwen3-tts-0.6b-customvoice')],status='running')
        p=self.home/'inventory.sqlite3';before=(p.stat().st_mtime_ns,hashlib.sha256(p.read_bytes()).hexdigest())
        readonly=Dashboard(self.home,read_only=True)
        with readonly.inventory.connect() as db:self.assertEqual(db.execute('PRAGMA query_only').fetchone()[0],1)
        readonly.query({'purpose':['tts']})
        self.assertEqual(before,(p.stat().st_mtime_ns,hashlib.sha256(p.read_bytes()).hexdigest()))
        with readonly.inventory.connect() as db:self.assertEqual(db.execute('SELECT status FROM scans').fetchone()[0],'running')
        missing=self.home/'not-created';empty=Dashboard(missing,read_only=True)
        self.assertEqual(empty.query({'purpose':['tts']})['rows'],[]);self.assertFalse(missing.exists())

    def test_invalid_purpose_and_unavailable_catalog_fail_closed(self):
        with self.assertRaises(ValueError):self.dashboard.query({'purpose':['unknown-purpose']})
        seed(self.dashboard,[self.group('qwen3-tts-0.6b-customvoice')])
        with patch('ai_manager.candidate_recommendations._profiles',side_effect=OSError('unavailable')):
            result=self.dashboard.query({'purpose':['tts']})
            self.assertEqual(result['recommendation']['recommended'],0)
            self.assertIn('catalog_unavailable',result['rows'][0]['recommendation']['reason_codes'])
