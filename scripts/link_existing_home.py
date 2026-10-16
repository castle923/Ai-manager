"""Explicitly link a new installation to a verified existing app home; no data copy."""
import argparse,hashlib,json,os
from pathlib import Path
import uuid


def safe_absolute(value):
    path=Path(value)
    if not path.is_absolute() or '..' in path.parts:raise ValueError('absolute_path_required')
    for item in (path,*path.parents):
        if item.is_symlink() or (item.exists() and getattr(item.lstat(),'st_file_attributes',0)&0x400):raise ValueError('reparse_path_rejected')
    return path


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--install',required=True);parser.add_argument('--home',required=True);parser.add_argument('--settings-sha256',required=True)
    args=parser.parse_args();install=safe_absolute(args.install);home=safe_absolute(args.home)
    if install==home or install in home.parents or home in install.parents:raise ValueError('overlapping_paths')
    settings=safe_absolute(home/'settings.json')
    if hashlib.sha256(settings.read_bytes()).hexdigest()!=args.settings_sha256.lower():raise ValueError('settings_hash_mismatch')
    target=safe_absolute(install/'installation.json');value=json.loads(target.read_text(encoding='utf-8-sig'))
    previous=install/'installation-before-home-link.json'
    with previous.open('xb') as stream:stream.write(target.read_bytes())
    value['app_home']=str(home);value['explicit_existing_home_link']=True;value['existing_settings_sha256']=args.settings_sha256.lower()
    temp=install/(uuid.uuid4().hex+'.json.tmp');temp.write_text(json.dumps(value,indent=2),encoding='utf-8');os.replace(temp,target)
    print(json.dumps({'status':'existing_home_linked','credentials_copied':False,'state_copied':False}))


if __name__=='__main__':
    try:main()
    except (OSError,ValueError,KeyError) as error:
        allowed={'absolute_path_required','reparse_path_rejected','overlapping_paths','settings_hash_mismatch'}
        code=str(error)
        print(json.dumps({'error':code if code in allowed else 'existing_home_link_failed'}))
        raise SystemExit(1)
