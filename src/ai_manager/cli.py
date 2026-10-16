"""Local M1 commands. Public output contains aggregates and controlled errors."""
import argparse
import json
import sys

from .auth import AuthError, AuthManager, client_config
from .config import SettingsStore, private_home
from .security import SecretStore


def services():
    home = private_home()
    settings = SettingsStore(home).load()
    return home, settings, AuthManager(settings, SecretStore(home / "credentials"))


def main():
    parser = argparse.ArgumentParser(description="Ai-manager M1: 두 계정 읽기 전용 모델 목록")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="명시 지정된 입력으로 새 앱 설정 생성")
    init.add_argument("--allowlist", required=True)
    init.add_argument("--client", required=True)
    for name in ("connect", "refresh", "disconnect", "scan"):
        p = sub.add_parser(name)
        p.add_argument("account", choices=["A", "B"])
    sub.add_parser("status")
    sub.add_parser("serve", help="로컬 M1 연결·수집 화면")
    args = parser.parse_args()
    try:
        if args.command == "init":
            client_config(args.client)
            SettingsStore(private_home()).initialize(args.allowlist, args.client)
            result = {"status": "initialized", "settings_version": 1}
        else:
            home, settings, auth = services()
            if args.command == "connect":
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
                result = {"credential_saved": {a: bool(auth.store.get(a)) for a in ("A", "B")}, "inventory": Inventory(home).summary()}
            else:
                from .server import serve
                serve(home, settings, auth)
                return
        print(json.dumps(result, ensure_ascii=False))
    except KeyboardInterrupt:
        print(json.dumps({"error": "cancelled"}))
        sys.exit(130)
    except AuthError as error:
        print(json.dumps({"error": str(error)}))
        sys.exit(1)
    except (ValueError, KeyError, OSError):
        print(json.dumps({"error": "configuration_or_local_io_failed"}))
        sys.exit(1)
    except Exception:
        # requests exceptions can contain request URLs. Never expose raw details.
        print(json.dumps({"error": "operation_failed_check_connection"}))
        sys.exit(1)


if __name__ == "__main__":
    main()
