"""Loopback-only M1 connection screen; no model execution or workspace product."""
import json
import secrets
import threading
import webbrowser
from pathlib import Path
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs

from .auth import AuthError


def serve(home, settings, auth, browser=webbrowser.open):
    from .inventory import Inventory
    from .dashboard import Dashboard
    csrf = secrets.token_urlsafe(32)
    job_lock = threading.Lock()
    cancel = threading.Event()
    task = {"status": "idle"}

    def state():
        return {"accounts": {a: {"credential_saved": bool(auth.store.get(a)), "roots": sum(r["account"] == a for r in settings["allowlist"])} for a in ("A", "B")},
                "task": dict(task), "inventory": Inventory(home).summary()}

    def work(action, account):
        try:
            if action == "connect":
                result = auth.connect(account, cancel=cancel)
            elif action == "refresh":
                auth.access(account, force_refresh=True)
                result = {"status": "refresh_verified"}
            elif action == "disconnect":
                result = auth.disconnect(account)
            else:
                result = Inventory(home).scan(settings, account, lambda force_refresh=False: auth.access(account, force_refresh=force_refresh), cancel=cancel)
            task.update(status="finished", result=result)
        except AuthError as error:
            task.update(status="failed", error=str(error))
        except Exception:
            task.update(status="failed", error="operation_failed_check_connection")
        finally:
            job_lock.release()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def allowed(self):
            expected = f"127.0.0.1:{self.server.server_port}"
            return self.headers.get("Host") == expected and self.headers.get("Origin", "http://" + expected) == "http://" + expected

        def reply(self, status, data, content_type="application/json; charset=utf-8"):
            body = data.encode() if isinstance(data, str) else json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if not self.allowed():
                return self.reply(403, {"error": "forbidden"})
            path = urlsplit(self.path).path
            if path == "/":
                entry = Path(__file__).parent / "static" / "index.html"
                if not entry.is_file():
                    return self.reply(503, "화면 빌드가 필요합니다. frontend에서 npm ci와 npm run build를 실행하세요.", "text/plain; charset=utf-8")
                return self.reply(200, entry.read_text(encoding="utf-8"), "text/html; charset=utf-8")
            if path.startswith("/assets/"):
                base = (Path(__file__).parent / "static" / "assets").resolve()
                asset = (base / path.removeprefix("/assets/")).resolve()
                if asset.parent != base or not asset.is_file() or asset.suffix not in {".js", ".css", ".svg"}:
                    return self.reply(404, {"error": "not_found"})
                return self.reply(200, asset.read_text(encoding="utf-8"), mimetypes.guess_type(str(asset))[0] or "text/plain")
            if path == "/api/session":
                return self.reply(200, {"csrf": csrf})
            if path in {"/api/dashboard", "/api/detail"}:
                try:
                    query = parse_qs(urlsplit(self.path).query)
                    dashboard = Dashboard(home)
                    result = dashboard.query(query) if path == "/api/dashboard" else dashboard.detail(query["id"][0], query.get("scan", [None])[0])
                    return self.reply(200, result)
                except ValueError:
                    return self.reply(400, {"error": "invalid_request"})
                except KeyError:
                    return self.reply(404, {"error": "not_found"})
            if path == "/app.js":
                return self.reply(200, "const csrf=" + json.dumps(csrf) + ";\n" + SCRIPT, "application/javascript; charset=utf-8")
            if path == "/style.css":
                return self.reply(200, STYLE, "text/css; charset=utf-8")
            if path == "/api/status":
                return self.reply(200, state())
            if path == "/api/files":
                import re
                try:
                    query = parse_qs(urlsplit(self.path).query)
                    scan_id = query["scan"][0]
                    offset = int(query.get("offset", ["0"])[0])
                    if not re.fullmatch(r"[a-f0-9]{32}", scan_id) or offset < 0:
                        raise ValueError()
                    return self.reply(200, {"files": Inventory(home).files(scan_id, limit=50, offset=offset)})
                except (ValueError, KeyError):
                    return self.reply(400, {"error": "invalid_request"})
            return self.reply(404, {"error": "not_found"})

        def do_POST(self):
            if not self.allowed() or not secrets.compare_digest(self.headers.get("X-AiManager-CSRF", ""), csrf):
                return self.reply(403, {"error": "forbidden"})
            if self.headers.get("Content-Type") != "application/json":
                return self.reply(415, {"error": "json_required"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 1024:
                    raise ValueError()
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict) or not isinstance(data.get("action"), str):
                    raise ValueError()
                action, account = data["action"], data.get("account")
                if account is not None and not isinstance(account, str):
                    raise ValueError()
                if self.path != "/api/action" or action not in ("connect", "refresh", "scan", "disconnect", "cancel") or (action != "cancel" and account not in ("A", "B")):
                    raise ValueError()
            except (ValueError, KeyError):
                return self.reply(400, {"error": "invalid_request"})
            if action == "cancel":
                cancel.set()
                return self.reply(202, {"status": "cancel_requested"})
            if not job_lock.acquire(blocking=False):
                return self.reply(409, {"error": "operation_running"})
            cancel.clear()
            task.clear()
            task.update(status="running", action=action, account=account)
            threading.Thread(target=work, args=(action, account), daemon=True).start()
            self.reply(202, {"status": "started"})

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        server.daemon_threads = True
        server.timeout = 1
        url = f"http://127.0.0.1:{server.server_port}/"
        print("Ai-manager 로컬 화면: " + url, flush=True)
        browser(url)
        server.serve_forever()


HTML = """<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Ai-manager · M1</title><link rel="stylesheet" href="/style.css"><body><main><p class="eyebrow">AI-MANAGER / M1</p><h1>내 모델 목록 연결</h1><p>두 계정의 지정 폴더를 읽기 전용으로 확인합니다. 파일 내용 다운로드와 모델 실행은 이후 단계입니다.</p><section id="accounts" aria-label="계정 연결"></section><section><h2>진행 상태</h2><p id="task" role="status" aria-live="polite"></p><button id="cancel">현재 작업 취소</button></section><section><h2>이번 앱의 수집 기록</h2><p>완료·부분 실패·과거 스캔을 구분합니다. 파일 발견은 구성·무결성·실행 검증을 뜻하지 않습니다.</p><label for="scan-select">조회할 수집 기록</label><select id="scan-select"></select><p id="inventory"></p><p id="scan-errors" role="status"></p><div class="table-wrap"><table><thead><tr><th scope="col">파일 이름</th><th scope="col">후보 종류</th><th scope="col">크기</th><th scope="col">수정일</th><th scope="col">발견 위치</th></tr></thead><tbody id="files"></tbody></table></div><p id="page-info"></p><button id="previous">이전 50개</button><button id="next">다음 50개</button></section><p id="error" role="alert"></p></main><script src="/app.js"></script></body></html>"""
SCRIPT = """
const labels={connect:'Google 로그인',refresh:'토큰 갱신 검증',scan:'허용 폴더 새로 수집',disconnect:'연결 해제'};
const statusLabels={idle:'대기 중',running:'진행 중',finished:'작업 완료',failed:'작업 실패',complete:'수집 완료',partial:'부분 수집 · 오류 있음',cancelled:'취소됨',interrupted:'중단됨'};
const errors={not_connected:'먼저 Google 로그인을 진행하세요.',account_mismatch:'지정한 계정과 로그인한 계정이 다릅니다.',unexpected_granted_scope:'실제 허용된 권한이 읽기 전용 범위와 다릅니다. 다시 연결하세요.',refresh_failed_reconnect_required:'토큰을 갱신하지 못했습니다. Google 로그인으로 다시 연결하세요.',authentication_cancelled:'로그인을 취소했습니다.',authentication_timeout:'로그인 대기 시간이 지났습니다.',consent_denied:'Google 권한 동의가 취소되었습니다.',operation_running:'다른 작업이 진행 중입니다.',operation_failed_check_connection:'작업을 완료하지 못했습니다. 연결 상태와 앱 설정을 확인하세요.',http_403:'폴더 접근 권한이 거부되었습니다.',http_404:'폴더를 찾을 수 없습니다.',http_401:'인증이 만료되었습니다. 다시 연결하세요.',incomplete_search:'Drive가 전체 검색을 완료하지 못했습니다.',network_error:'네트워크 연결에 실패했습니다.',process_interrupted:'이전 앱 실행이 중단되었습니다.',cancelled:'사용자가 수집을 취소했습니다.'};
const message=code=>errors[code]||'확인이 필요한 오류 ('+code+')';
let scans=[],offset=0,scanSignature='',filesSignature='';
errors.account_operation_busy='이 계정의 다른 인증 작업이 진행 중입니다. 완료 후 다시 시도하세요.';
const refreshFiles=()=>showFiles().catch(e=>document.getElementById('error').textContent=e.message);
const selector=document.getElementById('scan-select');
selector.onchange=()=>{offset=0;filesSignature='';refreshFiles();};
document.getElementById('previous').onclick=()=>{offset=Math.max(0,offset-50);refreshFiles();};
document.getElementById('next').onclick=()=>{offset+=50;refreshFiles();};
const accounts=document.getElementById('accounts');
for(const account of ['A','B']){
 const panel=document.createElement('article');const title=document.createElement('h2');title.textContent='계정 '+account;panel.append(title);
 const status=document.createElement('p');status.id='account-'+account;panel.append(status);
 for(const [action,label] of Object.entries(labels)){const button=document.createElement('button');button.textContent=label;button.onclick=()=>act(action,account);panel.append(button);}accounts.append(panel);
}
async function act(action,account){document.getElementById('error').textContent='';try{const r=await fetch('/api/action',{method:'POST',headers:{'Content-Type':'application/json','X-AiManager-CSRF':csrf},body:JSON.stringify({action,account})});const d=await r.json();if(!r.ok)throw new Error(message(d.error));await update();}catch(e){document.getElementById('error').textContent=e.message;}}
document.getElementById('cancel').onclick=()=>act('cancel');
async function showFiles(){const scan=scans.find(s=>s.scan_id===selector.value);if(!scan){document.getElementById('inventory').textContent='아직 수집 기록이 없습니다.';document.getElementById('files').replaceChildren();document.getElementById('previous').disabled=true;document.getElementById('next').disabled=true;document.getElementById('page-info').textContent='';document.getElementById('scan-errors').textContent='';return;}const signature=scan.scan_id+':'+scan.files_count+':'+scan.status+':'+offset;if(signature===filesSignature)return;filesSignature=signature;document.getElementById('inventory').textContent='계정 '+scan.account+' · '+(statusLabels[scan.status]||scan.status)+' · 후보 파일 '+scan.files_count+'개 / 폴더 '+scan.folders_count+'개 / 제외 '+scan.excluded_count+'개';document.getElementById('scan-errors').textContent=scan.errors.map(message).join(' / ');const r=await fetch('/api/files?scan='+encodeURIComponent(scan.scan_id)+'&offset='+offset);if(!r.ok){filesSignature='';throw new Error('수집 목록을 불러오지 못했습니다.');}const d=await r.json();const body=document.getElementById('files');body.replaceChildren();for(const f of d.files){const tr=document.createElement('tr');const m=f.metadata;const size=m.size===undefined?'미수집':Number(m.size).toLocaleString('ko-KR')+' B';for(const value of [m.name,({weight_candidate:'가중치 후보',model_component_candidate:'구성요소 후보',distribution_document_candidate:'배포 문서 후보'})[f.kind]||'미분류',size,m.modifiedTime?new Date(m.modifiedTime).toLocaleDateString('ko-KR'):'미수집',f.path]){const td=document.createElement('td');td.textContent=value;tr.append(td);}body.append(tr);}document.getElementById('page-info').textContent=d.files.length?(offset+1)+'–'+(offset+d.files.length)+' / '+scan.files_count+'개':'이 페이지에 파일이 없습니다.';document.getElementById('previous').disabled=offset===0;document.getElementById('next').disabled=offset+50>=scan.files_count;}
async function update(){try{const r=await fetch('/api/status');if(!r.ok)throw new Error('로컬 앱 응답을 확인하세요.');const d=await r.json();for(const a of ['A','B'])document.getElementById('account-'+a).textContent=(d.accounts[a].credential_saved?'자격 증명 저장됨 · 현재 인증은 갱신 검증 필요':'로그인 필요')+' · 허용 폴더 '+d.accounts[a].roots+'개';const t=d.task;document.getElementById('task').textContent=(statusLabels[t.status]||t.status)+(t.account?' · 계정 '+t.account:'')+(t.action?' · '+labels[t.action]:'')+(t.error?' · '+message(t.error):'');scans=d.inventory.scans||[];const signature=JSON.stringify(scans.map(s=>[s.scan_id,s.status]));if(signature!==scanSignature){scanSignature=signature;const old=selector.value;selector.replaceChildren();for(const [i,s]of scans.entries()){const op=document.createElement('option');op.value=s.scan_id;op.textContent=(i===0?'최근 기록':'과거 기록')+' · 계정 '+s.account+' · '+new Date(s.started_at).toLocaleString('ko-KR')+' · '+(statusLabels[s.status]||s.status);selector.append(op);}if(scans.some(s=>s.scan_id===old))selector.value=old;else offset=0;}await showFiles();}catch(e){document.getElementById('error').textContent=e.message;}}
update();setInterval(update,1500);
"""
STYLE = """:root{font:16px/1.65 system-ui,sans-serif;color:#172b3a;background:#f0f4f7}body{margin:0}main{max-width:1100px;margin:auto;padding:36px 20px}h1{font-size:2.2rem;line-height:1.25}h2{font-size:1.25rem}.eyebrow{color:#276574;font-weight:700;letter-spacing:.1em}section{margin:24px 0}#accounts{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:20px}article,section:not(#accounts){padding:24px;background:white;border:1px solid #c8d5df;border-radius:14px}button,select{font:inherit;font-weight:600;border:1px solid #48788a;color:#174e61;background:#eef8fc;border-radius:8px;padding:10px 14px;margin:4px;cursor:pointer}button:disabled{opacity:.5;cursor:default}button:focus-visible,select:focus-visible{outline:3px solid #bf5500;outline-offset:3px}select{max-width:100%;display:block}table{border-collapse:collapse;width:100%;font-size:.9rem}th,td{text-align:left;padding:12px;border-bottom:1px solid #d3dfe6;overflow-wrap:anywhere;min-width:90px;max-width:280px}th{background:#eef4f7}.table-wrap{overflow:auto}#task{white-space:pre-wrap}#error,#scan-errors{color:#a32424} @media(max-width:420px){main{padding:20px 12px}article,section:not(#accounts){padding:16px}button{display:block;width:100%;margin:8px 0}}"""
