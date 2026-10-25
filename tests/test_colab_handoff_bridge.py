"""Offline bridge tests: no Torch, weights, network, or existing homes."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import hashlib
import os
from ai_manager.colab_contract import build_request, validate_result

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'/'colab'))

class BridgeTests(unittest.TestCase):
    def module(self):
        path=ROOT/'scripts/colab/build_llama_handoff.py'
        self.assertTrue(path.exists(), 'manual public bridge is missing')
        import build_llama_handoff
        return build_llama_handoff

    def test_approval_default_never_reads_model(self):
        m=self.module()
        request=build_request('물은 얼면 무엇이 되나요?',m.source_pins())
        with patch.object(m,'runtime_versions',side_effect=AssertionError('runtime read')), patch.object(m,'verify_model',side_effect=AssertionError('model read')):
            result=m.run_request(json.dumps(request).encode(),Path('/not-a-model'),Path('/not-a-work'))
        self.assertEqual(result['reason'],'approval_required')
        validate_result(result,request)

    def test_bundle_public_only_and_no_overwrite(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'bundle'
            with patch.object(m.shutil,'disk_usage',return_value=type('Disk',(),{'free':600_000_000_000})()):
                value=m.build_bundle(out)
                self.assertLess(sum(p.stat().st_size for p in out.iterdir()),2_000_000)
                self.assertEqual(value['source_sha256'],m.source_pins())
                with self.assertRaises(ValueError):m.build_bundle(out)
            self.assertEqual((out/'model-manifest.json').read_bytes(),(ROOT/'src/ai_manager/adapter_manifest_llama.json').read_bytes())

    def test_runtime_source_model_rejections(self):
        m=self.module(); request=build_request('Hi',m.source_pins()); raw=json.dumps(request).encode()
        for seam,reason in [('runtime_versions','environment_unavailable'),('verify_sources','source_mismatch'),('verify_model','model_mismatch')]:
            with self.subTest(seam=seam), tempfile.TemporaryDirectory() as td:
                with patch.object(m,'runtime_versions',return_value=m.RUNTIME),patch.object(m,'verify_sources'),patch.object(m,'verify_model'),patch.object(m,'select_runtime_python',return_value=Path(sys.executable)),patch.object(m,seam,side_effect=ValueError('private details')):
                    result=m.run_request(raw,Path(td)/'model',Path(td)/'workspace',True)
                self.assertEqual(result['reason'],reason);validate_result(result,request)

    def test_one_attempt_fresh_context_and_guard_summary(self):
        m=self.module(); request=build_request('Hi',m.source_pins());raw=json.dumps(request).encode()
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);work=root/'new';model=root/'model';model.mkdir();(model/'sentinel').write_text('unchanged')
            selected=root/'approved-existing-venv'/'bin'/'python'
            old=root/'WORK';old.mkdir();(old/'watchdog-once.marker').write_text('old')
            def guard(command, run_dir, env, **kw):
                self.assertEqual(command[0],str(selected))
                self.assertEqual(kw['handshake_seconds'],240)
                self.assertEqual(env['HF_ENABLE_PARALLEL_LOADING'],'false')
                self.assertEqual(run_dir.name,request['request_id'])
                payload={'response':{'text':'얼음','input_tokens':4,'generated_tokens':2,'eos_reached':True,'length_cap_reached':False},'engine':m.ENGINE}
                (run_dir/'worker-result.json').write_text(json.dumps(payload))
                return dict(m.SUCCESS_GUARD)
            with patch.object(m,'runtime_versions',return_value=m.RUNTIME) as probe,patch.object(m,'verify_model'),patch.object(m,'select_runtime_python',return_value=selected),patch.object(m,'invoke_guard',side_effect=guard) as call:
                result=m.run_request(raw,model,work,True)
                self.assertEqual(result['status'],'success');validate_result(result,request)
                repeated=m.run_request(raw,model,work,True)
                self.assertEqual(repeated['reason'],'already_started');self.assertEqual(call.call_count,1)
                probe.assert_called_once_with(selected)
            self.assertEqual((old/'watchdog-once.marker').read_text(),'old')
            self.assertEqual((model/'sentinel').read_text(),'unchanged')

    def test_guard_stop_and_cleanup_never_become_success(self):
        m=self.module()
        for summary,reason in [(dict(m.SUCCESS_GUARD,status='stopped',reason='deadline_exceeded'),'guard_stopped'),(dict(m.SUCCESS_GUARD,remaining_owned_count=1),'cleanup_failed')]:
            with self.subTest(reason=reason),tempfile.TemporaryDirectory() as td:
                request=build_request('Hi',m.source_pins())
                with patch.object(m,'runtime_versions',return_value=m.RUNTIME),patch.object(m,'verify_model'),patch.object(m,'select_runtime_python',return_value=Path(sys.executable)),patch.object(m,'invoke_guard',return_value=summary):
                    result=m.run_request(json.dumps(request).encode(),Path(td)/'model',Path(td)/'new',True)
                self.assertEqual(result['reason'],reason);validate_result(result,request)

    def test_fake_tokenizer_model_bounds_and_eos_cap(self):
        self.module()
        import llama_handoff_worker as worker
        class IDs:
            ndim=2
            def __init__(self,n):self.shape=(1,n)
        class Tokenizer:
            def __init__(self,n):self.n=n
            def apply_chat_template(self,messages,**kw):
                self.messages=messages;return IDs(self.n)
        class Model:
            def __init__(self):self.calls=0
            def generate(self,**kw):self.calls+=1;self.kw=kw;return 'output'
        for count in (0,65):
            with self.assertRaises(worker.InputTokenLimit):worker.prepare_input(Tokenizer(count),'Hi')
        tokenizer=Tokenizer(4);ids=worker.prepare_input(tokenizer,'한글 e\u0301 <b>')
        self.assertEqual(tokenizer.messages,[{'role':'user','content':'한글 e\u0301 <b>'}])
        model=Model();worker.generate_once(model,ids,'mask',{2})
        self.assertEqual(model.calls,1);self.assertEqual(model.kw['max_new_tokens'],32);self.assertFalse(model.kw['do_sample'])
        self.assertEqual(worker.termination(2,2,{2}),(True,False))
        self.assertEqual(worker.termination(32,1,{2}),(False,True))
        self.assertEqual(worker.termination(32,2,{2}),(True,False))
        with self.assertRaises(ValueError):worker.termination(3,1,{2})

    def test_notebook_default_execution_preserves_old_globals(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as td,patch.object(m.shutil,'disk_usage',return_value=type('Disk',(),{'free':600_000_000_000})()):
            out=Path(td)/'bundle';m.build_bundle(out)
            state={'ROOT':'old-root','WORK':'old-work'}
            with patch('pathlib.Path.mkdir',side_effect=AssertionError('write')):
                for cell in json.loads((out/'Llama_App_Request.ipynb').read_bytes())['cells']:
                    if cell['cell_type']=='code':exec(''.join(cell['source']),state)
            self.assertFalse(state['APPROVE_ONE_REQUEST']);self.assertEqual(state['ROOT'],'old-root');self.assertEqual(state['WORK'],'old-work')

    def test_actual_source_tamper_and_existing_workspace_are_closed(self):
        m=self.module();request=build_request('Hi',m.source_pins())
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);model=root/'model';model.mkdir()
            with patch.object(m,'sha',return_value='0'*64),patch.object(m,'verify_model',side_effect=AssertionError('model read')):
                result=m.run_request(json.dumps(request).encode(),model,root/'fresh',True)
            self.assertEqual(result['reason'],'source_mismatch')
            old=root/'WORK';old.mkdir();(old/'marker').write_text('old')
            result=m.run_request(json.dumps(request).encode(),model,old,True)
            self.assertEqual(result['reason'],'already_started');self.assertEqual(list(old.iterdir()),[old/'marker'])

    def test_worker_failure_invalid_output_and_token_limit(self):
        m=self.module()
        for payload,summary,reason in [({},dict(m.SUCCESS_GUARD,worker_returncode=1,final_worker_returncode=1),'worker_failed'),({},m.SUCCESS_GUARD,'output_invalid'),({'reason':'input_token_limit'},m.SUCCESS_GUARD,'input_token_limit')]:
            with self.subTest(reason=reason),tempfile.TemporaryDirectory() as td:
                request=build_request('Hi',m.source_pins())
                def guard(command,work,env,**kw):
                    (work/'worker-result.json').write_text(json.dumps(payload));return summary
                with patch.object(m,'runtime_versions',return_value=m.RUNTIME),patch.object(m,'verify_model'),patch.object(m,'select_runtime_python',return_value=Path(sys.executable)),patch.object(m,'invoke_guard',side_effect=guard):
                    result=m.run_request(json.dumps(request).encode(),Path(td)/'model',Path(td)/'new',True)
                self.assertEqual(result['reason'],reason);validate_result(result,request)

    def test_changed_worker_context_rejected_before_model_access(self):
        import llama_handoff_worker as worker
        m=self.module();request=build_request('Hi',m.source_pins())
        with tempfile.TemporaryDirectory() as td:
            work=Path(td)/request['request_id'];work.mkdir();model=Path(td)/'model'
            (work/'app-request.once').write_text(request['request_sha256'])
            context=dict(request_sha256=request['request_sha256'],source_sha256=m.source_pins(),model_root=str(model),work=str(work))
            worker.validate_app_context(context,request,m.source_pins(),model,work)
            for key in context:
                changed=dict(context);changed[key]='changed'
                with self.assertRaises(ValueError):worker.validate_app_context(changed,request,m.source_pins(),model,work)

    def test_workspace_cannot_write_inside_model_root(self):
        m=self.module();request=build_request('Hi',m.source_pins())
        with tempfile.TemporaryDirectory() as td:
            model=Path(td)/'model';model.mkdir()
            with patch.object(m,'runtime_versions',return_value=m.RUNTIME),patch.object(m,'verify_model'),patch.object(m,'select_runtime_python',return_value=Path(sys.executable)),patch.object(m,'invoke_guard',side_effect=AssertionError('spawn')):
                result=m.run_request(json.dumps(request).encode(),model,model/'workspace',True)
            self.assertEqual(result['reason'],'model_mismatch');self.assertEqual(list(model.iterdir()),[])

    def test_actual_readonly_hash_core(self):
        import llama_handoff_worker as worker
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'synthetic.bin';raw=b'a'*(1024**2+4096)+b'end';path.write_bytes(raw)
            before=path.stat();hints=[]
            # Windows has no fadvise: inject only the advisory syscall, preserving
            # real descriptor/stat/read/hash/identity code on synthetic bytes.
            with patch.object(worker.os,'O_NOFOLLOW',getattr(os,'O_NOFOLLOW',0),create=True),patch.object(worker.os,'POSIX_FADV_DONTNEED',4,create=True):
                self.assertEqual(worker._verify_readonly(path,len(raw),hashlib.sha256(raw).hexdigest(),advise=lambda *args:hints.append(args)),hashlib.sha256(raw).hexdigest())
                with self.assertRaises(AssertionError):worker._verify_readonly(path,len(raw),'0'*64,advise=lambda *args:None)
            self.assertEqual(path.read_bytes(),raw);self.assertEqual(path.stat().st_mtime_ns,before.st_mtime_ns);self.assertTrue(hints)

    def test_selected_runtime_metadata_uses_bounded_subprocess(self):
        m=self.module()
        from types import SimpleNamespace
        selected=Path(sys.executable)
        with patch.object(m.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout=json.dumps(m.RUNTIME).encode(),stderr=b'')) as probe,patch.object(m.platform,'python_version',side_effect=AssertionError('kernel metadata')):
            self.assertEqual(m.runtime_versions(selected),m.RUNTIME)
        args,kw=probe.call_args;self.assertEqual(args[0][0],str(selected));self.assertEqual(args[0][1:3],['-I','-B']);self.assertLessEqual(kw['timeout'],10)
        self.assertNotIn('HF_TOKEN',kw['env']);self.assertEqual(kw['env']['HOME'],'')

    def test_runtime_probe_real_developer_interpreter_is_metadata_only(self):
        m=self.module()
        # Approved existing development interpreter, not any model/runtime install.
        # Its metadata is not the Colab contract; reject instead of installing.
        with patch.dict(os.environ,{'HF_TOKEN':'synthetic-not-secret'}):
            with self.assertRaises(ValueError):m.runtime_versions(Path(sys.executable))
        self.assertNotIn('torch',sys.modules)

    def test_selected_venv_is_exact_sibling_path(self):
        m=self.module()
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);model=root/'model';model.mkdir();expected=root/'venv'/'bin'/'python';expected.parent.mkdir(parents=True);expected.write_bytes(b'synthetic-not-executed')
            with patch.object(m,'validate_model_root',return_value=model):
                self.assertEqual(m.select_runtime_python(model),expected)
                self.assertEqual(m.select_runtime_python(model,expected),expected)
                with self.assertRaises(ValueError):m.select_runtime_python(model,Path(sys.executable))

    def test_invalid_model_structure_precedes_interpreter_probe(self):
        m=self.module();request=build_request('Hi',m.source_pins())
        with tempfile.TemporaryDirectory() as td,patch.object(m,'runtime_versions',side_effect=AssertionError('must not execute')):
            result=m.run_request(json.dumps(request).encode(),Path(td)/'model',Path(td)/'work',True,runtime_python=Path(sys.executable))
        self.assertEqual(result['reason'],'model_mismatch')

    def test_notebook_new_uuids_preserve_old_contexts_and_results(self):
        from types import SimpleNamespace
        m=self.module()
        with tempfile.TemporaryDirectory() as td,patch.object(m.shutil,'disk_usage',return_value=type('Disk',(),{'free':600_000_000_000})()):
            root=Path(td);out=root/'bundle';m.build_bundle(out)
            nb=json.loads((out/'Llama_App_Request.ipynb').read_bytes())
            state={'ROOT':'old-root','WORK':'old-work','PY':'old-python','APP_HANDOFF_CONTEXT':'old-singleton'}
            exec(''.join(nb['cells'][1]['source']),state)
            real_path=Path
            state['pathlib']=SimpleNamespace(Path=lambda value:root if value=='/content' else real_path(value))
            run=''.join(nb['cells'][2]['source']).replace('APPROVE_ONE_REQUEST=False','APPROVE_ONE_REQUEST=True')
            requests=[build_request('one',m.source_pins()),build_request('two',m.source_pins())]
            calls=[]
            original_loader=m.importlib.util.module_from_spec
            def load(spec):
                module=original_loader(spec)
                if spec.name=='app_request_bridge':
                    original_exec=spec.loader.exec_module
                    def execute(mod):
                        original_exec(mod)
                        def fake(raw,model,workspace,approved=False,**kw):
                            req=json.loads(raw);calls.append(req['request_id']);work=workspace/req['request_id'];work.mkdir(parents=True);(work/'app-request.once').write_text('once')
                            return m._result(req,'stopped','preflight','environment_unavailable')
                        mod.run_request=fake
                    spec.loader.exec_module=execute
                return module
            with patch.object(m.importlib.util,'module_from_spec',side_effect=load):
                for request in requests:
                    path=root/(request['request_id']+'.json');path.write_text(json.dumps(request))
                    exec(run.replace("REQUEST_PATH=''",'REQUEST_PATH='+repr(str(path))),state)
                contexts=dict(state['APP_HANDOFF_CONTEXTS']);self.assertEqual(len(contexts),2)
                self.assertEqual(len(set(contexts.values())),2)
                snapshots={path:(path/(key+'.result.json')).read_bytes() for key,path in contexts.items()}
                path=root/(requests[0]['request_id']+'.json')
                with self.assertRaisesRegex(RuntimeError,'already_started'):exec(run.replace("REQUEST_PATH=''",'REQUEST_PATH='+repr(str(path))),state)
                self.assertEqual(len(calls),2)
                with self.assertRaises(FileNotFoundError):exec(run.replace("REQUEST_PATH=''",'REQUEST_PATH='+repr(str(root/'missing.json'))),state)
                self.assertEqual(state['APP_HANDOFF_CONTEXTS'],contexts)
                for key,path in contexts.items():self.assertEqual((path/(key+'.result.json')).read_bytes(),snapshots[path])
            self.assertEqual([state[k] for k in ('ROOT','WORK','PY','APP_HANDOFF_CONTEXT')],['old-root','old-work','old-python','old-singleton'])
            markdown=''.join(nb['cells'][0]['source'])
            self.assertNotIn('Disconnect and delete',markdown)
            self.assertIn('Preserve',markdown)

if __name__=='__main__':unittest.main()
