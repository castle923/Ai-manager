"""Independent WebView2 desktop host; no global Python or browser-tab UI."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
from urllib.parse import urlsplit
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .auth import AuthManager, client_config
from .config import SettingsStore, private_home
from .desktop_files import save_output
from .desktop_install import install_to_new_directory
from .runtime_bootstrap import RuntimeBootstrap
from .security import SecretStore
from .server import create_application
from .external_process import spawn_external
from .runtime_paths import configure_desktop_runtime


def open_oauth_browser(url):
    # Only OAuth uses a system browser. Do not change the OS browser setting.
    for root in (os.environ.get('PROGRAMFILES(X86)'), os.environ.get('PROGRAMFILES')):
        if root:
            executable = Path(root) / 'Microsoft/Edge/Application/msedge.exe'
            if executable.is_file():
                spawn_external([str(executable), url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
    import webbrowser
    return webbrowser.open(url)


class DesktopAuth(AuthManager):
    def connect(self, account, cancel=None, timeout=300, browser=None):
        return super().connect(account, cancel=cancel, timeout=timeout, browser=open_oauth_browser)


class DesktopBridge:
    def __init__(self, home, resources, package_root):
        self._home, self._resources, self._package_root = home, resources, package_root
        self._window, self._application = None, None
        self._guard_ready = False
        self._selected = {}
        self._dialog_lock = threading.Lock()
        self._close_lock, self._setup_close_lock = threading.Lock(), threading.Lock()
        self._closed = False
        self._runtime = RuntimeBootstrap(home, resources)
        self._setup_server, self._setup_thread, self._setup_url = None, None, None
        self._model_thread, self._model_preparation = None, None
        self._model_cancel = threading.Event()
        self._model_admission = threading.Lock()
        self._model_state = {'status': 'idle'}

    def _host_status(self, **values):
        # Deliberately omit URLs, queries, titles, input content and raw exceptions.
        from .preparation import atomic_text
        path = private_home(self._home / 'host-status.json')
        previous = json.loads(path.read_text()) if path.is_file() else {}
        previous.update(values)
        atomic_text(path, json.dumps(previous, indent=2))

    def _trusted(self, setup=False):
        if self._window is None or not self._guard_ready:
            return False
        current = self._window.get_current_url()
        if self._application is None:
            return setup and current == self._setup_url and self._setup_url is not None
        expected, actual = urlsplit(self._application.url), urlsplit(current or '')
        return not setup and (actual.scheme, actual.netloc, actual.path) == (expected.scheme, expected.netloc, '/') and not actual.query

    def choose_setup_file(self, kind):
        if not self._trusted(setup=True) or kind not in ('client', 'allowlist'):
            return {'status': 'denied'}
        import webview
        with self._dialog_lock:
            result = self._window.create_file_dialog(webview.FileDialog.OPEN, allow_multiple=False, file_types=('JSON (*.json)',))
        if not result:
            return {'status': 'cancelled'}
        self._selected[kind] = str(private_home(result[0]))
        return {'status': 'selected', 'kind': kind, 'filename': Path(result[0]).name}

    def set_setup_path(self, kind, value):
        if not self._trusted(setup=True) or kind not in ('client', 'allowlist') or not isinstance(value, str):
            return {'status': 'denied'}
        try:
            path = private_home(value.strip())
            if not path.is_file() or path.suffix.casefold() != '.json':
                return {'status': 'failed', 'error': 'setup_original_file_required'}
            self._selected[kind] = str(path)
            return {'status': 'selected', 'kind': kind, 'filename': path.name}
        except (OSError, ValueError):
            return {'status': 'failed', 'error': 'setup_original_file_required'}

    def initialize(self):
        if not self._trusted(setup=True) or set(self._selected) != {'client', 'allowlist'}:
            return {'status': 'denied', 'error': 'select_both_original_inputs'}
        try:
            client_config(self._selected['client'])
            SettingsStore(self._home).initialize(self._selected['allowlist'], self._selected['client'])
            self._start_application()
            self._window.load_url(self._application.url)
            self._close_setup()
            return {'status': 'initialized'}
        except Exception:
            return {'status': 'failed', 'error': 'setup_inputs_invalid_or_already_initialized'}

    def install(self, parent_path=None):
        if not self._trusted(setup=True) or not getattr(sys, 'frozen', False):
            return {'status': 'denied'}
        import webview
        try:
            if parent_path is not None:
                if not isinstance(parent_path, str):
                    return {'status': 'failed', 'error': 'installation_parent_invalid'}
                parent = private_home(parent_path.strip())
                if not parent.is_dir():
                    return {'status': 'failed', 'error': 'installation_parent_invalid'}
            else:
                with self._dialog_lock:
                    selected = self._window.create_file_dialog(webview.FileDialog.FOLDER)
                if not selected:
                    return {'status': 'cancelled'}
                parent = private_home(selected[0])
            if not self._trusted(setup=True):
                return {'status': 'denied'}
            target = parent / 'AiManager-0.7.1'
            self._host_status(installation_stage='validating_and_copying', installation_target_preexisted=target.exists())
            result = install_to_new_directory(self._package_root, target, self._home)
            self._host_status(installation_stage='installed', installation_files_verified=result['files_verified'])
            result['message'] = f'설치 완료: {target}\n이 폴더의 AiManager.exe를 실행하세요. 현재 창은 닫아도 됩니다.'
            return result
        except Exception as error:
            allowed = {'installation_paths_overlap', 'installation_destination_exists', 'installation_version_invalid', 'installation_integrity_failed', 'installation_copy_integrity_failed', 'installation_executable_missing'}
            code = str(error) if str(error) in allowed else 'installation_failed_preserve_existing_files'
            self._host_status(installation_stage='failed', installation_error=code, installation_errno=getattr(error, 'errno', None), installation_winerror=getattr(error, 'winerror', None))
            result = {'status': 'failed', 'error': code}
            if code == 'installation_destination_exists':
                result['message'] = f'설치 대상이 이미 있습니다: {target}\n기존 폴더는 보존했습니다. 다른 상위 폴더를 선택해주세요.'
            return result

    def runtime_status(self):
        if not self._trusted():
            return {'status': 'denied'}
        return self._runtime.snapshot()

    def prepare_runtime(self):
        if not self._trusted():
            return {'status': 'denied'}
        return self._runtime.start()

    def model_status(self):
        if not self._trusted():
            return {'status': 'denied'}
        if self._model_thread and self._model_thread.is_alive() and self._model_preparation:
            snapshot = self._model_preparation.snapshot()['preparation']
            return dict(self._model_state, status='running', files_verified=snapshot.get('files_verified', 0), total_bytes=snapshot.get('total_bytes', 0), downloaded_bytes=snapshot.get('downloaded_bytes', 0), preflight=snapshot.get('preflight'))
        return dict(self._model_state)

    def prepare_model(self, model_id, source_path=None):
        if not self._model_admission.acquire(False):
            return {'status': 'running'}
        try:
            return self._prepare_model(model_id, source_path)
        finally:
            self._model_admission.release()

    def _prepare_model(self, model_id, source_path=None):
        from .models import model_ids
        if not self._trusted() or model_id not in model_ids():
            return {'status': 'denied'}
        if self._model_thread and self._model_thread.is_alive():
            return {'status': 'running'}
        if self._application.inference.active is not None:
            return {'status': 'failed', 'error': 'inference_running'}
        if source_path is None:
            import webview
            with self._dialog_lock:
                selected = self._window.create_file_dialog(webview.FileDialog.FOLDER)
            if not selected:
                return {'status': 'cancelled'}
            if not isinstance(selected, (tuple, list)) or len(selected) != 1 or not isinstance(selected[0], str):
                self._model_state = {'status': 'failed', 'model_id': model_id, 'error': 'model_folder_selection_invalid'}
                return dict(self._model_state)
            source_path = selected[0]
        if not self._trusted():
            return {'status': 'denied'}
        try:
            if not isinstance(source_path, str) or not source_path.strip() or len(source_path) > 32767 or any(c in source_path for c in '\x00\r\n'):
                raise ValueError('model_folder_invalid')
            source = private_home(source_path.strip())
            if not source.is_dir():
                raise ValueError('model_folder_invalid')
        except (OSError, ValueError):
            self._model_state = {'status': 'failed', 'model_id': model_id, 'error': 'model_folder_absolute_directory_required'}
            return dict(self._model_state)
        from .preparation import Preparation
        settings = SettingsStore(self._home).load()
        auth = DesktopAuth(settings, SecretStore(self._home / 'credentials'))
        self._model_preparation = Preparation(self._home, settings, auth, model_id=model_id)
        preparation = self._model_preparation
        self._model_cancel.clear()
        self._model_state = {'status': 'running', 'model_id': model_id, 'source_directory': str(source)}
        def work():
            try:
                state = preparation.prepare_local(source, cancel=self._model_cancel)
                self._model_state = dict(self._model_state, status=state['status'], files_verified=state['files_verified'], preflight=state.get('preflight'))
            except Exception:
                try:
                    failed = preparation.snapshot()['preparation']
                except Exception:
                    failed = {}
                self._model_state = dict(self._model_state, status='cancelled' if self._model_cancel.is_set() else 'failed', error=failed.get('error') or 'model_preparation_failed_check_designated_folder', preflight=failed.get('preflight'))
        self._model_thread = threading.Thread(target=work, daemon=True)
        self._model_thread.start()
        return dict(self._model_state)

    def cancel_model(self):
        if not self._trusted():
            return {'status': 'denied'}
        self._model_cancel.set()
        return {'status': 'cancelling'}

    def save_audio(self, run_id):
        if not self._trusted() or self._application is None:
            return {'status': 'denied'}
        import re
        if not isinstance(run_id, str) or not re.fullmatch('[a-f0-9]{32}', run_id):
            return {'status': 'failed', 'error': 'run_not_found'}
        import webview
        with self._dialog_lock:
            inference = self._application.inference
            try:
                if not inference.owner.handle or inference.get(run_id)['status'] != 'succeeded':
                    return {'status': 'failed', 'error': 'output_not_ready'}
                selected = self._window.create_file_dialog(webview.FileDialog.SAVE, save_filename=run_id + '.wav', file_types=('WAV (*.wav)',))
                if not selected:
                    return {'status': 'cancelled'}
                if not self._trusted():
                    return {'status': 'denied'}
                return save_output(inference, run_id, selected[0])
            except Exception:
                return {'status': 'failed', 'error': 'save_failed_use_new_destination'}

    def _start_application(self):
        settings = SettingsStore(self._home).load()
        auth = DesktopAuth(settings, SecretStore(self._home / 'credentials'))
        self._application = create_application(self._home, settings, auth)
        self._application.start()

    def _close(self):
        with self._close_lock:
            if self._closed:
                return
            self._closed = True
        self._model_cancel.set()
        try:
            if self._model_thread:
                self._model_thread.join(20)
        finally:
            try:
                self._runtime.close()
            finally:
                try:
                    if self._application:
                        self._application.close()
                finally:
                    self._close_setup()

    def _start_setup(self):
        content = SETUP_HTML.encode('utf-8')
        class SetupHandler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                expected = f'127.0.0.1:{self.server.server_port}'
                allowed = self.headers.get('Host') == expected and self.headers.get('Origin', 'http://' + expected) == 'http://' + expected
                status = 200 if allowed and self.path == '/' else 403 if not allowed else 404
                body = content if status == 200 else b'Not available'
                self.send_response(status)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
                self.send_header('X-Frame-Options', 'DENY')
                self.end_headers()
                self.wfile.write(body)
        self._setup_server = ThreadingHTTPServer(('127.0.0.1', 0), SetupHandler)
        self._setup_server.daemon_threads = True
        self._setup_url = f'http://127.0.0.1:{self._setup_server.server_port}/'
        self._setup_thread = threading.Thread(target=self._setup_server.serve_forever, daemon=True)
        self._setup_thread.start()

    def _close_setup(self):
        with self._setup_close_lock:
            server, thread = self._setup_server, self._setup_thread
            self._setup_server, self._setup_thread = None, None
        if server:
            try:
                server.shutdown()
            finally:
                server.server_close()
                thread.join(5)

    def _install_navigation_guard(self):
        # pywebview exposes the native WebView2 control through window.native.
        # Restrict top-level navigation before any page may call the bridge.
        def starting(sender, event):
            uri = str(event.Uri)
            if self._application is None:
                allowed = uri == self._setup_url
            else:
                expected, actual = urlsplit(self._application.url), urlsplit(uri)
                allowed = (actual.scheme, actual.netloc, actual.path) == (expected.scheme, expected.netloc, '/') and not actual.query
            if not allowed:
                event.Cancel = True
            self._host_status(navigation_allowed=allowed, navigation_scheme=urlsplit(uri).scheme,
                              navigation_about_blank=uri == 'about:blank')
        try:
            self._navigation_handler = starting
            self._window.native.webview.NavigationStarting += starting
            def initialized(sender, event):
                self._host_status(webview_initialized=bool(event.IsSuccess),
                                  webview_error_hresult=None if event.IsSuccess else int(event.InitializationException.HResult))
            self._initialization_handler = initialized
            self._window.native.webview.CoreWebView2InitializationCompleted += initialized
            self._guard_ready = True
            self._host_status(navigation_guard_ready=True)
        except Exception:
            self._guard_ready = False
            self._window.native.Close()


SETUP_HTML = r'''<!doctype html><html lang="ko"><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'">
<title>Ai-manager · 처음 시작</title><style>
body{font:16px/1.8 'Malgun Gothic',sans-serif;color:#213753;background:#f6f8fb;margin:0}main{max-width:700px;padding:36px;margin:auto}h1{font-size:30px}section{background:white;border:1px solid #dce4ef;border-radius:14px;padding:24px;margin:20px 0}button{font:inherit;color:#fff;background:#245caf;border:0;border-radius:7px;padding:10px 16px;margin:7px 7px 7px 0;cursor:pointer}button:focus-visible,input:focus-visible{outline:3px solid #bb6200;outline-offset:4px}p{color:#526889}#message{white-space:pre-wrap}input{box-sizing:border-box;font:inherit;width:100%;border:1px solid #8798b2;border-radius:6px;padding:8px 10px}label{display:block;margin-top:10px}small{color:#526889}</style>
<main><p>AI-MANAGER / WINDOWS · 0.7.1</p><h1>내 모델 작업실, 처음 시작</h1><p>Python 별도 설치 없이 독립 앱 창에서 사용합니다. 모델·계정 정보는 이 패키지에 포함되지 않습니다.</p>
<section><h2>지정 원본으로 새 설정</h2><p>이번 프로젝트에 지정된 OAuth client JSON과 allowlist JSON을 선택하세요. 계정 로그인은 다음 화면에서 시스템 브라우저로 직접 진행합니다.</p>
<button onclick="choose('client')">OAuth client 선택</button><span id="client">미선택</span><label for="client-path">또는 OAuth client 원본 전체 경로</label><input id="client-path" placeholder="지정 JSON의 절대경로"><button onclick="setPath('client')">OAuth client 경로 적용</button>
<br><button onclick="choose('allowlist')">허용 목록 선택</button><span id="allowlist">미선택</span><label for="allowlist-path">또는 허용 목록 원본 전체 경로</label><input id="allowlist-path" placeholder="지정 JSON의 절대경로"><button onclick="setPath('allowlist')">허용 목록 경로 적용</button><br><button onclick="initializeApp()">새 작업실 시작</button></section>
<section><h2>실행 위치 선택</h2><p>압축을 푼 현재 위치에서도 실행할 수 있습니다. 설치는 선택한 상위 폴더 안에 새 AiManager-0.7.1 폴더를 만들며 기존 대상이 있으면 덮어쓰지 않습니다.</p><label for="install-path">설치할 상위 폴더 전체 경로 (선택)</label><input id="install-path" oninput="previewInstall()" placeholder="비워두면 폴더 선택 대화상자를 엽니다"><p id="install-target">생성될 앱 폴더: 선택한 상위 폴더 안의 AiManager-0.7.1</p><button onclick="installApp()">사용자 폴더에 설치</button></section><p id="message" role="status" aria-live="polite">설정 원본을 선택해주세요.</p></main>
<script>const out=x=>document.getElementById('message').textContent=x;function previewInstall(){const p=document.getElementById('install-path').value.trim();document.getElementById('install-target').textContent='생성될 앱 폴더: '+(p?p.replace(/[\\/]+$/,'')+'/AiManager-0.7.1':'선택한 상위 폴더 안의 AiManager-0.7.1')}async function choose(k){const r=await pywebview.api.choose_setup_file(k);if(r.status==='selected')document.getElementById(k).textContent=r.filename;else out(r.status==='cancelled'?'선택을 취소했습니다.':'선택할 수 없습니다.')}async function setPath(k){const r=await pywebview.api.set_setup_path(k,document.getElementById(k+'-path').value);if(r.status==='selected'){document.getElementById(k).textContent=r.filename;out('지정 원본 경로를 적용했습니다.')}else out('존재하는 지정 JSON의 전체 절대경로를 확인해주세요.')}async function initializeApp(){out('설정을 확인합니다…');const r=await pywebview.api.initialize();if(r.status!=='initialized')out('두 지정 JSON과 새 작업실 상태를 확인해주세요.')}async function installApp(){const p=document.getElementById('install-path').value.trim();out(p?'앱 파일을 확인하고 새 폴더에 설치합니다…':'설치할 상위 폴더를 선택해주세요.');const r=await pywebview.api.install(p||null);out(r.message||(r.status==='cancelled'?'설치를 취소했습니다.':r.error==='installation_destination_exists'?'이 상위 폴더에 AiManager-0.7.1이 이미 있습니다. 다른 상위 폴더를 선택해주세요.':'설치할 기존 상위 폴더의 전체 경로와 저장 공간을 확인해주세요. 기존 자료는 보존됩니다.'));}</script></html>'''


def main():
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    parser = argparse.ArgumentParser()
    parser.add_argument('--home')
    args = parser.parse_args()
    bridge = None
    try:
        home = private_home(args.home or str(Path(os.environ['LOCALAPPDATA']) / 'AiManager' / 'desktop-0.7.1'))
        SettingsStore(home)  # Protect the new home before profile or runtime state exists.
        resources = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2]))
        configure_desktop_runtime(resources)
        package_root = Path(sys.executable).parent if getattr(sys, 'frozen', False) else resources
        bridge = DesktopBridge(home, resources, package_root)
        import webview
        webview.settings['ALLOW_DOWNLOADS'] = False
        webview.settings['ALLOW_FILE_URLS'] = False
        webview.settings['OPEN_EXTERNAL_LINKS_IN_BROWSER'] = False
        if (home / 'settings.json').is_file():
            bridge._start_application()
        else:
            bridge._start_setup()
        window = webview.create_window('Ai-manager · 내 모델 작업실', url=bridge._application.url if bridge._application else bridge._setup_url,
                                       js_api=bridge, width=1280, height=900,
                                       min_size=(768, 620), text_select=True)
        bridge._window = window
        window.events.before_show += bridge._install_navigation_guard
        window.events.closed += bridge._close
        webview.start(gui='edgechromium', debug=False, private_mode=False, storage_path=str(private_home(home / 'webview-profile')))
    except Exception:
        ctypes.windll.user32.MessageBoxW(None, '앱 창을 시작하지 못했습니다. 앱 파일·작업실 설정·Microsoft Edge WebView2 Runtime 설치 상태를 확인하세요. 보안 설정을 변경하거나 다른 렌더러로 전환하지 않습니다.', 'Ai-manager 시작 확인', 0x10)
    finally:
        if bridge:
            bridge._close()


if __name__ == '__main__':
    main()
