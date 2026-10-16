import contextlib,hashlib,io,json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from ai_manager.config import private_home
from ai_manager.preparation import Preparation,PreparationError
from ai_manager.cli import main

class M6InstallationTests(unittest.TestCase):
    def test_explicit_absolute_home_preserves_default(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(private_home(temp),Path(temp).resolve())
        with self.assertRaises(ValueError):private_home('relative-home')
        self.assertEqual(private_home().name,'m1-20261016')

    def test_cli_custom_home_port_and_no_browser(self):
        with tempfile.TemporaryDirectory() as temp,patch('sys.argv',['ai-manager','--home',temp,'serve','--port','2966','--no-browser']),patch('ai_manager.cli.services',return_value=(Path(temp),{},object())) as services,patch('ai_manager.server.serve') as serve:
            main();services.assert_called_once_with(Path(temp).resolve())
            self.assertEqual(serve.call_args.kwargs['port'],2966)
            self.assertIsNone(serve.call_args.kwargs['browser']('http://invalid.test'))

    def test_cli_invalid_port_does_not_start_services(self):
        with patch('sys.argv',['ai-manager','serve','--port','65536']),patch('ai_manager.cli.services') as services,contextlib.redirect_stdout(io.StringIO()),self.assertRaises(SystemExit):main()
        services.assert_not_called()

class M6LocalPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.home=self.root/'home';self.source=self.root/'source';self.source.mkdir();self.content=b'fresh M6 synthetic model bytes'
        (self.source/'config.json').write_bytes(self.content)
        self.manifest={'model_id':'qwen3-tts-0.6b-customvoice','name':'synthetic/model','revision':'new-test-revision','source':'https://example.invalid/official','files':[{'path':'config.json','size':len(self.content),'sha256':hashlib.sha256(self.content).hexdigest()}]}
        self.patch=patch('ai_manager.preparation.manifest',return_value=self.manifest);self.patch.start();self.addCleanup(self.patch.stop)

    def test_manifest_only_new_ids_hashes_no_old_state_copy(self):
        (self.source/'state.json').write_text('must not copy');(self.source/'prior.wav').write_bytes(b'not allowed')
        prep=Preparation(self.home);first=prep.prepare_local(self.source);second=prep.prepare_local(self.source)
        self.assertNotEqual(first['id'],second['id']);self.assertEqual(first['status'],'ready');self.assertEqual(first['files_verified'],1)
        assets=prep.base/first['id']/'assets';self.assertEqual([p.name for p in assets.iterdir()],['config.json'])
        self.assertEqual((assets/'config.json').read_bytes(),self.content)
        provenance=json.loads((assets.parent/'inputs.json').read_text());self.assertEqual(provenance['files'][0]['sha256'],self.manifest['files'][0]['sha256'])

    def test_bad_hash_and_missing_component_fail_preserve_source(self):
        (self.source/'config.json').write_bytes(b'x'*len(self.content))
        with self.assertRaisesRegex(PreparationError,'hash_mismatch'):Preparation(self.home).prepare_local(self.source)
        self.assertEqual((self.source/'config.json').read_bytes(),b'x'*len(self.content))
        state=json.loads((self.home/'preparations/current.json').read_text());self.assertEqual(state['status'],'failed')

    @unittest.skipUnless(os.name=='nt','Windows junction boundary')
    def test_junction_source_escape_rejected(self):
        link=self.root/'junction';result=subprocess.run(['cmd','/c','mklink','/J',str(link),str(self.source)],capture_output=True)
        self.assertEqual(result.returncode,0)
        with self.assertRaisesRegex(ValueError,'unsafe_local_path'):Preparation(self.home).prepare_local(link)

    @unittest.skipUnless(os.name=='nt','Windows junction boundary')
    def test_nested_junction_component_escape_rejected(self):
        self.manifest['files'][0]['path']='sub/config.json'
        result=subprocess.run(['cmd','/c','mklink','/J',str(self.source/'sub'),str(self.source)],capture_output=True);self.assertEqual(result.returncode,0)
        with self.assertRaisesRegex(ValueError,'unsafe_local_path'):Preparation(self.home).prepare_local(self.source)
