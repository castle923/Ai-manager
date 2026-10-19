"""Actual localhost API checks against new synthetic metadata only."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import requests
from ai_manager.dashboard import Dashboard
from ai_manager.inventory import Inventory
from ai_manager.server import create_application
from test_candidate_recommendations import profile,root_files,seed


class Auth:
    class Store:
        def get(self,account):return None
    store=Store()


class RecommendationHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.home=Path(self.temp.name)
        self.app=create_application(self.home,{'allowlist':[]},Auth());self.url=self.app.start().rstrip('/')
        groups=[]
        for identifier in ('qwen3-tts-0.6b-customvoice','qwen3-tts-1.7b-customvoice','whisper-large-v3-turbo','qwen-image-2.1','llama-3.1-8b-instruct','tapir'):
            p=profile(identifier);groups.append(dict(path=p['name'].rsplit('/',1)[-1],files=root_files(p)))
        seed(Dashboard(self.home),groups)
        self.session=requests.Session();self.session.trust_env=False

    def tearDown(self):self.session.close();self.app.close();self.temp.cleanup()

    def get(self,path='/api/dashboard',**params):return self.session.get(self.url+path,params=params,timeout=5)

    def test_five_purposes_have_independent_metadata_policy_not_runtime_claims(self):
        for purpose,count in (('tts',2),('stt',1),('image',0),('llm',1),('tracking',1)):
            response=self.get(purpose=purpose);self.assertEqual(response.status_code,200)
            value=response.json();self.assertEqual(value['recommendation']['purpose'],purpose)
            self.assertEqual(value['recommendation']['recommended'],count)
            self.assertTrue(all(r['recommendation']['execution']=='unverified' for r in value['rows']))
            if purpose=='image':self.assertGreater(value['recommendation']['related'],0)
        self.assertEqual(self.get().json()['recommendation']['recommended'],0)

    def test_detail_is_current_purpose_and_does_not_invent_filtered_rank(self):
        row=self.get(purpose='tts').json()['rows'][0]
        detail=self.get('/api/detail',id=row['id'],scan=row['scan_id'],purpose='tts').json()
        self.assertEqual(detail['recommendation']['purpose'],'tts');self.assertTrue(detail['recommendation']['eligible']);self.assertIsNone(detail['recommendation']['rank'])
        changed=self.get('/api/detail',id=row['id'],scan=row['scan_id'],purpose='stt').json()
        self.assertFalse(changed['recommendation']['eligible']);self.assertIsNone(changed['recommendation']['rank'])
        self.assertEqual(self.get('/api/detail',id=row['id'],purpose='unapproved').status_code,400)

    def test_recommendation_get_opens_read_only_and_keeps_inventory_bytes(self):
        db=self.home/'inventory.sqlite3';before=(db.stat().st_mtime_ns,hashlib.sha256(db.read_bytes()).hexdigest())
        with patch('ai_manager.dashboard.Inventory',wraps=Inventory) as constructor:
            for purpose in ('tts','stt','image','tracking'):
                self.assertEqual(self.get(purpose=purpose).status_code,200)
            self.assertTrue(all(call.kwargs.get('read_only') is True for call in constructor.call_args_list))
        self.assertEqual(before,(db.stat().st_mtime_ns,hashlib.sha256(db.read_bytes()).hexdigest()))
        self.assertEqual(self.get('/api/tts/status').json()['runs'],[])
        self.assertEqual(self.get('/api/tasks/status').json()['runs'],[])
        self.assertEqual(self.get('/api/registry').json()['summary']['registered'],0)

    def test_invalid_queries_and_host_origin_guards_remain(self):
        for query in ({'purpose':'tts<script>'},{'sort':'quality_score'},{'limit':'101'}):self.assertEqual(self.get(**query).status_code,400)
        self.assertEqual(self.session.get(self.url+'/api/dashboard?purpose=tts',headers={'Origin':'https://foreign.invalid'},timeout=5).status_code,403)
        self.assertEqual(self.session.get(self.url+'/api/dashboard?purpose=tts',headers={'Host':'foreign.invalid'},timeout=5).status_code,403)

    def test_file_mode_and_cross_filters_preserve_empty_not_fallback(self):
        for sort in ('recommendation','name','size','modified'):
            value=self.get(purpose='tts',view='files',sort=sort).json()
            self.assertEqual(value['recommendation']['unit'],'file_relevance_only')
            self.assertTrue(all(r['recommendation']['rank'] is None for r in value['rows']))
        value=self.get(purpose='tts',account='B').json()
        self.assertEqual(value['rows'],[]);self.assertEqual(value['recommendation']['recommended'],0)
