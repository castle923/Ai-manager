"""Build a fresh Windows wheel bundle from an explicit source allowlist."""
import argparse
import hashlib
import importlib.metadata
import platform
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    output=Path(args.output)
    if not output.is_absolute() or '..' in output.parts or output.exists():
        raise SystemExit('Use a new absolute output directory; existing files are preserved.')
    if any(p.is_symlink() or (p.exists() and getattr(p.lstat(),'st_file_attributes',0)&0x400) for p in (output,*output.parents)): raise SystemExit('Reparse output paths are not supported.')
    source=output/'source';dist=output/'release';source.mkdir(parents=True);dist.mkdir()
    files=[root/'pyproject.toml',*sorted((root/'src/ai_manager').glob('*.py')),*sorted((root/'src/ai_manager').glob('model_manifest*.json')),root/'src/ai_manager/static/index.html',*sorted((root/'src/ai_manager/static/assets').glob('*'))]
    provenance=[]
    for path in files:
        if not path.is_file() or path.is_symlink(): raise SystemExit('Source allowlist contains a non-regular file.')
        rel=path.relative_to(root);target=source/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
        provenance.append({'path':rel.as_posix(),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    subprocess.run([sys.executable,'-m','pip','wheel','--disable-pip-version-check','--no-deps','--no-build-isolation','--wheel-dir',str(dist),str(source)],check=True)
    wheels=list(dist.glob('*.whl'))
    if len(wheels)!=1:raise SystemExit('Expected one freshly built wheel.')
    with zipfile.ZipFile(wheels[0]) as archive:
        names=archive.namelist()
        for expected in ['ai_manager/download_diagnostics.py','ai_manager/cli.py','ai_manager/static/index.html','ai_manager/model_manifest.json','ai_manager/model_manifest_1.7b.json']:
            if expected not in names: raise SystemExit('Required package component absent: '+expected)
        if any('credentials' in name or '.dpapi' in name or name.endswith('.wav') for name in names): raise SystemExit('Private asset in wheel.')
    for relative in ['requirements.lock','requirements-runtime.lock','scripts/install_windows.ps1','scripts/setup_runtime.ps1','scripts/link_existing_home.py','docs/INSTALL.md','docs/RECOVERY.md']:
        original=root/relative
        if not original.is_file(): raise SystemExit('Required release guidance absent: '+relative)
        destination=dist/(Path(relative).name if relative=='scripts/install_windows.ps1' else relative)
        destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(original,destination)
    (dist/'README.txt').write_text('Ai-manager 0.6.0 for Windows\nRead docs/INSTALL.md and docs/RECOVERY.md.\nRequires Python 3.10. This bundle is not a standalone executable.\nDo not copy old credentials, inventory, run state or generated output into a new home.\n',encoding='utf-8')
    manifest={'build_environment':{'python':platform.python_version(),'packages':{name:importlib.metadata.version(name) for name in ('pip','setuptools','wheel')}},'schema_version':1,'version':'0.6.0','source_files':provenance,'wheel_entries':names,'artifacts':[{'name':p.relative_to(dist).as_posix(),'size':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(dist.rglob('*')) if p.is_file()]}
    (dist/'MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    bundle=output/'ai-manager-0.6.0-windows.zip'
    with zipfile.ZipFile(bundle,'x',compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(dist.rglob('*')):
            if path.is_file():archive.write(path,path.relative_to(dist).as_posix())
    print(json.dumps({'status':'built','wheel':wheels[0].name,'sha256':hashlib.sha256(wheels[0].read_bytes()).hexdigest(),'source_files':len(provenance),'wheel_entries':len(names),'bundle_sha256':hashlib.sha256(bundle.read_bytes()).hexdigest()}))


if __name__=='__main__':main()
