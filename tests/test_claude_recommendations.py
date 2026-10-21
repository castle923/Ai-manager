"""New synthetic-only tests. Never read real keys or call a provider."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from ai_manager.claude_recommendations import (
    ClaudeRecommendations, RecommendationError, COUNT_PATH, MESSAGE_PATH, MODEL, strict_json)


class FakeSource:
    def __init__(self):
        self.version = 1
        self.reverse = False
    def _catalog(self):
        return [(json.dumps({'model_id':'synthetic-'+t}).encode(),t) for t in ('tts','stt','llm','image','tracking')]
    def _candidates(self, task, profiles, catalog, include_unrelated=False):
        values = [dict(id='a'*64,name='New private model label',fingerprint='v'+str(self.version),file_count=3,size_bytes=0,profile_hints=[],local_related=False,reasons=['미확인']),
                  dict(id='b'*64,name='speech_tokenizer',fingerprint='b1',file_count=1,size_bytes=None,profile_hints=[],local_related=True,reasons=['구성요소'])]
        return list(reversed(values)) if self.reverse else values


class FakeKeys:
    def __init__(self, present=True):self.present=present;self.reads=0
    def exists(self):return self.present
    def save(self,key):self.present=True
    def read(self):self.reads+=1;return 'sk-ant-only-new-synthetic-test-key'


class FakeTransport:
    def __init__(self):self.calls=[];self.count_hook=None;self.message_hook=None
    def post(self,path,body,key,event):
        self.calls.append((path,deepcopy(body)))
        hook=self.count_hook if path==COUNT_PATH else self.message_hook
        if hook:return hook(body,event)
        if path==COUNT_PATH:return {'input_tokens':1000}
        user=json.loads(body['messages'][0]['content'])
        rows=[]
        for item in user['candidates']:
            ev=item['evidence'];name=next((x for x in ev if x['code']=='name_hint'),None)
            component=item['entity_kind'] in {'component','adapter'}
            rows.append(dict(candidate_id=item['candidate_id'],category=user['purpose'] if name else 'unknown',
                relevance='low' if component else 'high' if name else 'unknown',entity_kind=item['entity_kind'],
                evidence_ids=[(name or ev[0])['id']],reason_codes=[(name or ev[0])['code']]))
        order={'high':3,'medium':2,'low':1,'unknown':0};rows.sort(key=lambda x:-order[x['relevance']])
        return dict(model=MODEL,stop_reason='end_turn',content=[dict(type='text',text=json.dumps({'items':rows}))],usage=dict(input_tokens=1000,output_tokens=200,cache_creation_input_tokens=0,cache_read_input_tokens=0))


class ClaudeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.home=Path(self.temp.name);self.source=FakeSource();self.keys=FakeKeys();self.transport=FakeTransport()
        self.service=ClaudeRecommendations(self.home,{},source=self.source,keys=self.keys,transport=self.transport)
        self.addCleanup(self.service.close)
    def preview(self, count=2, include=True, amount='0.01'):
        data=self.service.overview('stt')
        selected=[dict(id=x['id'],fingerprint=x['fingerprint'],display_name=x['name'],include_name=include) for x in data['candidates'][:count]]
        return self.service.preview(dict(task='stt',selections=selected,max_usd=amount))
    def run_preview(self,p):
        result=self.service.run(dict(preview_id=p['preview_id'],approval_hash=p['approval_hash'],acknowledged=True))
        self.service.threads[result['job_id']].join(3)
        self.assertFalse(self.service.threads[result['job_id']].is_alive())
        return self.service.overview('stt')
    def failure(self, code, method, data):
        with self.assertRaisesRegex(RecommendationError,code):method(data)
    def test_preview_and_get_are_local_no_key_read_no_network_payload_minimized(self):
        before={p.name:p.read_bytes() for p in self.home.iterdir() if p.is_file() and p.suffix!=".lock"}
        p=self.preview();self.assertEqual(self.transport.calls,[]);self.assertEqual(self.keys.reads,0)
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.home.iterdir() if p.is_file() and p.suffix!=".lock"})
        text=json.dumps(p['exact_payload']);self.assertNotIn('a'*64,text);self.assertNotIn('fingerprint',text)
        self.assertEqual(p['count_payload'],{k:v for k,v in p['exact_payload'].items() if k not in {'max_tokens','stream','service_tier'}})
        self.assertFalse(self.service.overview('stt')['execution_allowed'])
    def test_consent_false_unknown_fields_and_one_use(self):
        p=self.preview();self.failure('consent_required',self.service.run,dict(preview_id=p['preview_id'],approval_hash=p['approval_hash'],acknowledged=False))
        result=self.run_preview(p);self.assertEqual(result['job']['status'],'finished')
        self.failure('already_consumed',self.service.run,dict(preview_id=p['preview_id'],approval_hash=p['approval_hash'],acknowledged=True))
        self.assertEqual([x[0] for x in self.transport.calls],[COUNT_PATH,MESSAGE_PATH])
    def test_count_and_message_same_approved_fields_and_result_reasons_rank(self):
        data=self.run_preview(self.preview());self.assertEqual(data['job']['cost_state'],'observed')
        count,message=[x[1] for x in self.transport.calls]
        self.assertEqual(count,{k:v for k,v in message.items() if k not in {'max_tokens','stream','service_tier'}})
        self.assertEqual(data['latest_result']['items'][0]['rank'],1)
        self.assertIn('승인한 모델 표시명',data['latest_result']['items'][0]['reasons'][0])
        self.assertTrue(any('선택 작업 음성 인식과 일치' in x for x in data['latest_result']['items'][0]['reasons']))
        self.assertEqual(data['latest_result']['items'][1]['entity_kind'],'component')
    def test_source_stale_before_dispatch_consumes_no_network(self):
        p=self.preview();self.source.version+=1
        self.failure('preview_stale',self.service.run,dict(preview_id=p['preview_id'],approval_hash=p['approval_hash'],acknowledged=True))
        self.assertEqual(self.transport.calls,[]);self.assertEqual(self.keys.reads,0)
    def test_count_to_messages_stale_means_paid_zero(self):
        def change(body,event):self.source.version+=1;return {'input_tokens':1000}
        self.transport.count_hook=change
        result=self.run_preview(self.preview())
        self.assertEqual([x[0] for x in self.transport.calls],[COUNT_PATH]);self.assertEqual(result['job']['status'],'failed')
        self.assertEqual(result['job']['cost_state'],'observed')
    def test_count_cancel_means_paid_zero_and_cancel_route_not_locked(self):
        entered=threading.Event();release=threading.Event()
        def wait(body,event):entered.set();release.wait(2);return {'input_tokens':1000}
        self.transport.count_hook=wait;p=self.preview()
        job=self.service.run(dict(preview_id=p['preview_id'],approval_hash=p['approval_hash'],acknowledged=True))
        self.assertTrue(entered.wait(2));self.service.cancel({'job_id':job['job_id']});release.set();self.service.threads[job['job_id']].join(3)
        result=self.service.overview('stt');self.assertEqual(result['job']['status'],'cancelled');self.assertEqual(result['job']['cost_state'],'observed')
        self.assertEqual(len(self.transport.calls),1)
    def test_budget_rejection_before_paid_call(self):
        data=self.run_preview(self.preview(amount='0.000001'))
        self.assertEqual(len(self.transport.calls),1);self.assertEqual(data['job']['error_code'],'provider_budget_blocked');self.assertEqual(data['job']['cost_state'],'observed')
    def test_paid_timeout_retains_unknown_reservation_and_blocks_next(self):
        def timeout(body,event):raise RecommendationError('provider_timeout')
        self.transport.message_hook=timeout;data=self.run_preview(self.preview())
        self.assertEqual(data['job']['status'],'cost_unknown');self.assertEqual(data['job']['cost_state'],'unknown')
        p=self.preview();self.failure('provider_budget_blocked',self.service.run,dict(preview_id=p['preview_id'],approval_hash=p['approval_hash'],acknowledged=True))
    def test_second_owner_rejected_without_changing_first_running(self):
        with self.assertRaisesRegex(RecommendationError,'provider_busy'):
            ClaudeRecommendations(self.home,{},source=self.source,keys=self.keys,transport=self.transport)
        self.assertEqual(self.service.overview('stt')['job'],None)
        self.run_preview(self.preview());self.assertEqual(len(self.transport.calls),2)
    def test_restart_keeps_protected_result_without_alias_rebinding_or_plaintext(self):
        data=self.run_preview(self.preview());original_id=data['latest_result']['items'][0]['id'];self.service.close()
        raw=(self.home/'claude-recommendations.sqlite3').read_bytes();self.assertNotIn(b'New private model label',raw);self.assertNotIn(b'speech_tokenizer',raw)
        self.source.reverse=True
        other=ClaudeRecommendations(self.home,{},source=self.source,keys=self.keys,transport=self.transport);self.addCleanup(other.close)
        result=other.overview('stt')['latest_result'];self.assertFalse(result['stale']);self.assertEqual(result['items'][0]['id'],original_id)
        self.assertTrue(result['items'][0]['evidence']);self.source.version+=1;self.assertTrue(other.overview('stt')['latest_result']['stale'])
        for p in (self.home/'claude-protected-results').glob('*.dpapi'):self.assertNotIn(b'New private model label',p.read_bytes())
    def test_schema_rejects_cross_candidate_evidence_and_entity_upgrade(self):
        p=self.preview();v=self.service.previews[p['preview_id']]
        response=self.transport.post(MESSAGE_PATH,v['body'],'fake',threading.Event());out=json.loads(response['content'][0]['text'])
        out['items'][0]['evidence_ids']=['c02e01'];response['content'][0]['text']=json.dumps(out)
        self.failure('provider_response_invalid',lambda _:self.service._validate(response,v),None)
        response=self.transport.post(MESSAGE_PATH,v['body'],'fake',threading.Event());out=json.loads(response['content'][0]['text']);out['items'][1]['entity_kind']='model_candidate';response['content'][0]['text']=json.dumps(out)
        self.failure('provider_response_invalid',lambda _:self.service._validate(response,v),None)
    def test_size_only_cannot_claim_task_high_and_zero_not_unknown(self):
        p=self.preview(include=False);v=self.service.previews[p['preview_id']]
        user=json.loads(v['body']['messages'][0]['content']);self.assertEqual(user['candidates'][0]['evidence'][2]['value'],0)
        response=self.transport.post(MESSAGE_PATH,v['body'],'fake',threading.Event());out=json.loads(response['content'][0]['text']);out['items'][0]['category']='stt';out['items'][0]['relevance']='high';response['content'][0]['text']=json.dumps(out)
        self.failure('provider_response_invalid',lambda _:self.service._validate(response,v),None)
    def test_strict_json_duplicates_nan_and_preview_controls_rejected(self):
        for raw in ('{"a":1,"a":2}','{"a":NaN}'):
            with self.assertRaises(RecommendationError):strict_json(raw)
        base=self.service.overview('stt')['candidates'][0]
        for name in ('/home/private/model','bad\nlabel','bad\u202elabel','someone@example.invalid','C:\\private\\model'):
            with self.subTest(name_kind='synthetic-invalid'):
                self.failure('invalid_request',self.service.preview,dict(task='stt',selections=[dict(id=base['id'],fingerprint=base['fingerprint'],display_name=name,include_name=True)],max_usd='0.01'))
    def test_refusal_truncation_unknown_usage_preserves_paid_accounting(self):
        real=self.transport.post
        def invalid(body,event):
            self.transport.message_hook=None
            response=real(MESSAGE_PATH,body,'fake',event);response['stop_reason']='max_tokens';return response
        self.transport.message_hook=invalid;data=self.run_preview(self.preview())
        self.assertEqual(data['job']['status'],'failed');self.assertEqual(data['job']['cost_state'],'observed');self.assertEqual(data['job']['error_code'],'provider_output_incomplete')
    def test_expiry_limit_and_dpapi_failure_no_plaintext(self):
        for _ in range(8):self.preview(count=1)
        with self.assertRaisesRegex(RecommendationError,'provider_busy'):self.preview(count=1)
        with patch.object(self.keys,'save',side_effect=RecommendationError('provider_key_unavailable')):
            self.failure('provider_key_unavailable',self.service.save_key,{'api_key':'sk-ant-new-synthetic-key-only'})
        self.assertFalse(any(p.suffix in {'.txt','.json'} for p in self.home.iterdir()))

    def test_close_keeps_owner_until_inflight_worker_finishes(self):
        entered=threading.Event();release=threading.Event()
        def wait(body,event):entered.set();release.wait(2);return {'input_tokens':1000}
        self.transport.count_hook=wait;p=self.preview()
        job=self.service.run(dict(preview_id=p['preview_id'],approval_hash=p['approval_hash'],acknowledged=True))
        self.assertTrue(entered.wait(2));self.service.close()
        with self.assertRaisesRegex(RecommendationError,'provider_busy'):
            ClaudeRecommendations(self.home,{},source=self.source,keys=self.keys,transport=self.transport)
        release.set();self.service.threads[job['job_id']].join(3)
        other=ClaudeRecommendations(self.home,{},source=self.source,keys=self.keys,transport=self.transport);self.addCleanup(other.close)
        self.assertEqual(other.overview('stt')['job']['cost_state'],'observed')
        self.assertEqual(len(self.transport.calls),1)

    def test_contract_change_expires_result_without_resending(self):
        self.run_preview(self.preview())
        with patch('ai_manager.claude_recommendations.SYSTEM','new synthetic contract'):
            self.assertTrue(self.service.overview('stt')['latest_result']['stale'])
        self.assertEqual(len(self.transport.calls),2)

    def test_key_read_source_change_prevents_count_dispatch(self):
        def change():
            self.source.version+=1
            return 'sk-ant-only-new-synthetic-test-key'
        with patch.object(self.keys,'read',side_effect=change):
            data=self.run_preview(self.preview())
        self.assertEqual(self.transport.calls,[])
        self.assertEqual(data['job']['error_code'],'provider_result_stale')

    def test_protected_result_failure_preserves_observed_paid_usage(self):
        with patch.object(self.service.result_store,'save',side_effect=RecommendationError('provider_result_storage_unavailable')):
            data=self.run_preview(self.preview())
        self.assertEqual(data['job']['status'],'failed')
        self.assertEqual(data['job']['error_code'],'provider_result_storage_unavailable')
        self.assertEqual(data['job']['cost_state'],'observed')
        self.assertEqual(json.loads(self.service._rows()[0]['usage_json'])['output_tokens'],200)
        self.assertIsNone(data['latest_result'])

if __name__=='__main__':unittest.main()
