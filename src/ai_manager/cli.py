"""Local inventory and preparation commands with controlled status output."""
import argparse
import json
import sys

from .auth import AuthError, AuthManager, client_config
from .config import SettingsStore, private_home
from .security import SecretStore


def services(home=None):
    home = private_home(home)
    settings = SettingsStore(home).load()
    from .local_mode import is_local, NoDriveAuth
    auth = NoDriveAuth() if is_local(settings) else AuthManager(settings, SecretStore(home / "credentials"))
    return home, settings, auth


def main():
    parser = argparse.ArgumentParser(description="Ai Manager: 읽기 전용 모델 조회와 선정 자산 준비")
    parser.add_argument("--home", help="명시적 절대경로의 별도 앱 홈; 기존 홈을 복사하지 않음")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-local", help="새 작업실에만 Drive 미연결 로컬 설정 생성")
    init = sub.add_parser("init", help="명시 지정된 입력으로 새 앱 설정 생성")
    init.add_argument("--allowlist", required=True)
    init.add_argument("--client", required=True)
    for name in ("connect", "refresh", "disconnect", "scan"):
        p = sub.add_parser(name)
        p.add_argument("account", choices=["A", "B"])
    sub.add_parser("prepare", help="승인된 첫 모델의 새 로컬 준비")
    local = sub.add_parser("prepare-local", help="명시 지정한 모델 파일만 새 준비 실행으로 복사·해시 검증")
    from .models import model_ids
    local.add_argument("--model-id", choices=model_ids(), required=True)
    local.add_argument("--source", required=True)
    sub.add_parser("runtime-check", help="독립 추론 환경 import/CUDA 검사, 추론 없음")
    sub.add_parser("preparation-status")
    sub.add_parser("status")
    backup = sub.add_parser("db-backup", help="SQLite backup API로 새 파일에만 일관 스냅샷 생성")
    backup.add_argument("--destination", required=True)
    restore = sub.add_parser("db-restore", help="검증한 DB를 새 대상에만 복원; 기존 DB 보존")
    restore.add_argument("--source", required=True)
    restore.add_argument("--destination", required=True)
    server_parser = sub.add_parser("serve", help="로컬 모델 조회·준비 대시보드")
    server_parser.add_argument("--port", type=int, default=0, help="loopback 포트; 기본값은 자동 선택")
    server_parser.add_argument("--no-browser", action="store_true", help="브라우저 자동 열기 생략")
    args = parser.parse_args()
    try:
        selected_home = private_home(args.home)
        if args.command == "serve" and not 0 <= args.port <= 65535:
            raise ValueError("Invalid loopback port")
        if args.command in ("db-backup", "db-restore"):
            from .db_recovery import copy_database_to_new_target
            result = copy_database_to_new_target(selected_home / "inventory.sqlite3" if args.command == "db-backup" else args.source, args.destination)
        elif args.command == "init-local":
            if not args.home:
                raise ValueError('explicit_new_local_home_required')
            SettingsStore(selected_home).initialize_local()
            result = {"status": "initialized", "settings_version": 2, "mode": "local"}
        elif args.command == "init":
            client_config(args.client)
            SettingsStore(selected_home).initialize(args.allowlist, args.client)
            result = {"status": "initialized", "settings_version": 1}
        else:
            home, settings, auth = services(selected_home)
            from .local_mode import is_local
            if is_local(settings) and args.command in ('connect', 'refresh', 'disconnect', 'scan', 'prepare'):
                raise AuthError('drive_setup_required')
            if args.command == "prepare-local":
                from .preparation import Preparation
                state = Preparation(home, settings, auth, model_id=args.model_id).prepare_local(args.source)
                result = {key: state[key] for key in ("id", "status", "files_verified", "downloaded_bytes", "integrity")}
            elif args.command in ("prepare", "runtime-check", "preparation-status"):
                from .preparation import Preparation
                prep = Preparation(home, settings, auth)
                result = prep.prepare() if args.command == "prepare" else prep.probe_runtime() if args.command == "runtime-check" else prep.snapshot()
            elif args.command == "connect":
                print("시스템 브라우저에서 지정 계정에 로그인하세요. 최대 5분 대기합니다.", flush=True)
                result = auth.connect(args.account)
            elif args.command == "refresh":
                auth.access(args.account, force_refresh=True)
                result = {"account": args.account, "status": "refresh_verified"}
            elif args.command == "disconnect":
                result = auth.disconnect(args.account)
            elif args.command == "scan":
                from .inventory import Inventory
                result = Inventory(home).scan(settings, args.account, lambda force_refresh=False: auth.access(args.account, force_refresh=force_refresh))
            elif args.command == "status":
                from .inventory import Inventory
                from .local_mode import account_status, drive_status
                result = {"credential_saved": {a:v['credential_saved'] for a,v in account_status(settings,auth).items()}, "drive":drive_status(settings), "inventory": Inventory(home).summary()}
            else:
                from .server import serve
                options = {"port": args.port}
                if args.no_browser:
                    options["browser"] = lambda url: None
                serve(home, settings, auth, **options)
                return
        print(json.dumps(result, ensure_ascii=False))
    except KeyboardInterrupt:
        print(json.dumps({"error": "cancelled"}))
        sys.exit(130)
    except AuthError as error:
        print(json.dumps({"error": str(error)}))
        sys.exit(1)
    except (ValueError, KeyError, OSError) as error:
        safe_errors = {"database_integrity_failed", "database_schema_unsupported", "database_source_missing", "database_destination_exists", "database_unreadable_or_corrupt", "database_backup_timeout", "absolute_database_paths_required", "unsafe_local_path"}
        code = str(error)
        print(json.dumps({"error": code if code in safe_errors else "configuration_or_local_io_failed"}))
        sys.exit(1)
    except Exception:
        # requests exceptions can contain request URLs. Never expose raw details.
        print(json.dumps({"error": "operation_failed_check_connection"}))
        sys.exit(1)


if __name__ == "__main__":
    main()
