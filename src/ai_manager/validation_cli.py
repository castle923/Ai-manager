"""M12 local-user control CLI. No model execution, network preparation, or UI changes."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
import uuid
from .validation_contracts import ContractError,fail,identifier
from .validation_intake import observe_local,safe_path,metadata_json
from .validation_store import ValidationStore,build_plan,packed
from .validation_coordinator import Coordinator


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home',required=True,help='New, isolated M12 control home')
    parser.add_argument('--auth-home',help='Explicit M12 OAuth home for live Drive reobservation')
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('init')
    scan=sub.add_parser('scan-local');scan.add_argument('--root',required=True);scan.add_argument('--alias',default='local')
    scan.add_argument('--depth',type=int,default=8);scan.add_argument('--json-bytes',type=int,default=262144);scan.add_argument('--read-bytes',type=int,default=2097152)
    drive=sub.add_parser('scan-drive');drive.add_argument('--account',choices=['A','B'],required=True);drive.add_argument('--root-id',required=True)
    drive.add_argument('--depth',type=int,default=2)
    plan=sub.add_parser('plan');plan.add_argument('--observation',required=True);plan.add_argument('--cpu-probe',action='store_true')
    plan.add_argument('--wall-seconds',type=int,default=300);plan.add_argument('--probe-seconds',type=int,default=1);plan.add_argument('--probe-timeout',type=int,default=10)
    approve=sub.add_parser('approve');approve.add_argument('--plan',required=True);approve.add_argument('--sha256',required=True)
    approve.add_argument('--confirm',action='store_true',help='Explicit current local OS-user confirmation; not Google OAuth')
    consume=sub.add_parser('dispatch');consume.add_argument('--plan',required=True);consume.add_argument('--approval',required=True)
    for name in ('run','status','cancel'):
        p=sub.add_parser(name);p.add_argument('--batch',required=True)
    args=parser.parse_args(argv)
    try:
        def drive_reobserve(previous):
            if not args.auth_home:fail('live_drive_auth_home_required')
            from .validation_drive import authenticated_provider
            return authenticated_provider(Path(args.auth_home),previous['account'],previous['root_id'],**previous['scope']).reobserve(previous)
        store=ValidationStore(Path(args.home),initialize=args.command=='init',reobserver=drive_reobserve)
        if args.command=='init':result=dict(status='initialized',store_id=store.store_id)
        elif args.command in ('scan-local','scan-drive'):
            if args.command=='scan-local':observation=observe_local(args.root,alias=args.alias,depth_limit=args.depth,json_limit=args.json_bytes,read_limit=args.read_bytes)
            else:
                if not args.auth_home:fail('live_drive_auth_home_required')
                from .validation_drive import authenticated_provider
                observation=authenticated_provider(Path(args.auth_home),args.account,args.root_id,depth_limit=args.depth).observe()
            folder=store.home/'observations'
            folder.mkdir(exist_ok=True);safe_path(store.home,'observations')
            oid=uuid.uuid4().hex
            with (folder/(oid+'.json')).open('x',encoding='utf-8') as stream:stream.write(packed(observation))
            result=dict(status='observed',observation_id=oid,fingerprint=observation['fingerprint'],complete=observation['complete'],
                        read_bytes=observation['read_bytes'],candidates=observation['candidates'])
        elif args.command=='plan':
            identifier(args.observation)
            path=safe_path(store.home,'observations/'+args.observation+'.json')
            if path.stat().st_size>4194304:fail('observation_size_limit')
            observation=metadata_json(path.read_bytes(),maximum=4194304,node_limit=65536)
            result=store.save_plan(build_plan(observation,action='run_cpu_probe' if args.cpu_probe else 'validate_control_plan',
                wall_seconds=args.wall_seconds,probe_seconds=args.probe_seconds,timeout_seconds=args.probe_timeout))
        elif args.command=='approve':result=store.approve(args.plan,args.sha256,confirmed=args.confirm)
        elif args.command=='dispatch':result=store.consume(args.plan,args.approval)
        elif args.command=='run':result=Coordinator(store).run(args.batch)
        elif args.command=='status':result=store.status(args.batch)
        else:
            store.cancel(args.batch);result=dict(status='cancel_requested')
        result['model_test_performed']=False
        print(json.dumps(result,ensure_ascii=True,allow_nan=False))
        return 0
    except ContractError as exc:
        print(json.dumps(dict(status='rejected',reason=str(exc),model_test_performed=False)));return 2
    except (OSError,ValueError,sqlite3.Error,KeyError,TypeError):
        print(json.dumps(dict(status='rejected',reason='control_io_or_schema_failed',model_test_performed=False)));return 2
    except Exception:
        print(json.dumps(dict(status='rejected',reason='control_operation_failed',model_test_performed=False)));return 2


if __name__=='__main__':sys.exit(main())
