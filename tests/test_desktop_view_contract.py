"""Run real UI fragment helpers with Node, then check the unchanged native boundary."""
import json
from pathlib import Path
import re
import shutil
import subprocess
from types import SimpleNamespace
import unittest
from ai_manager.desktop import DesktopBridge

ROOT = Path(__file__).resolve().parents[1]

class DesktopViewContractTests(unittest.TestCase):
    def node(self, program):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node is required for the frontend/native joint contract')
        helper = (ROOT/'frontend/src/workspace.ts').read_text(encoding='utf8').split('export type ViewPreferences')[0]
        helper = helper.replace('export function', 'function').replace('params: URLSearchParams', 'params')
        result = subprocess.run([node, '-e', helper + program], capture_output=True, text=True, encoding='utf8', timeout=10, check=True)
        return json.loads(result.stdout)

    def trusted(self, url):
        bridge = DesktopBridge.__new__(DesktopBridge)
        bridge._guard_ready = True
        bridge._application = SimpleNamespace(url='http://127.0.0.1:54321/')
        bridge._window = SimpleNamespace(get_current_url=lambda: url)
        return bridge._trusted()

    def test_real_fragment_helpers_preserve_reload_state_and_native_trust(self):
        result = self.node("""
        global.location = new URL('http://127.0.0.1:54321/');
        global.history = {replaceState:(_,__,url)=>{location=new URL(url)}};
        const p=appViewParams();
        for(const [key,value] of Object.entries({section:'tts',source_kind:'run',source_id:'a'.repeat(32),h_q:'새 음성',h_kind:'run',h_offset:'25',h_selected:'run:'+ 'a'.repeat(32)}))p.set(key,value);
        replaceAppView(p);
        console.log(JSON.stringify({url:location.href,query:location.search,restored:Object.fromEntries(appViewParams())}));
        """)
        self.assertEqual(result['query'], '')
        self.assertTrue(self.trusted(result['url']))
        self.assertEqual(result['restored']['source_id'], 'a'*32)
        self.assertEqual(result['restored']['h_q'], '새 음성')
        self.assertEqual(result['restored']['h_offset'], '25')
        self.assertEqual(result['restored']['h_selected'], 'run:'+'a'*32)

    def test_native_query_origin_path_and_guard_remain_fail_closed(self):
        for url in ('http://127.0.0.1:54321/?section=tts', 'http://127.0.0.1:54321/?x=1#section=tts',
                    'http://127.0.0.1:54322/#section=tts', 'https://example.com/#section=tts',
                    'http://127.0.0.1:54321/other#section=tts'):
            with self.subTest(url=url):self.assertFalse(self.trusted(url))
        result=self.node("""global.location=new URL('http://127.0.0.1:54321/?x=1');global.history={replaceState:(_,__,u)=>location=new URL(u)};const p=appViewParams();p.set('section','history');replaceAppView(p);console.log(JSON.stringify(location.href));""")
        self.assertFalse(self.trusted(result))

    def test_actual_source_parser_from_fragment_blocks_invalid_original(self):
        source=(ROOT/'frontend/src/main.tsx').read_text(encoding='utf8')
        parser=source.split('  function sourceFromUrl() {',1)[1].split('  const [registration',1)[0]
        parser='function sourceFromUrl() {'+parser
        parser=re.sub(r' as Record<\s*string,\s*string\s*>', '', parser)
        program=parser+"""
        const cases=[['tts','run','a'.repeat(32)],['comparison','comparison','b'.repeat(32)],['library','scan','c'.repeat(32)],['tts','scan','d'.repeat(32)],['library','run','d'.repeat(32)],['tts','run','bad'],['','run','a'.repeat(32)]];
        console.log(JSON.stringify(cases.map(([section,kind,id])=>{global.location=new URL('http://127.0.0.1:54321/#'+new URLSearchParams({section,source_kind:kind,source_id:id}));return !!sourceFromUrl()})));
        """
        self.assertEqual(self.node(program),[True,True,True,False,False,False,False])

if __name__ == '__main__':unittest.main()
