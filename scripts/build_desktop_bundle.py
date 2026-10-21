"""Fresh Windows onedir application with a verified complete local Python base."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
import importlib.metadata

PYTHON_URL = 'https://github.com/astral-sh/python-build-standalone/releases/download/20261009/cpython-3.10.22%2B20261009-x86_64-pc-windows-msvc-install_only.tar.gz'
PYTHON_SHA256 = 'cb023e83e42d8937ba77c7cf83641083c3b81e88e1226e1c694a347ae1924d54'
PYTHON_BYTES = 39573204
IMAGE_PYTHON_URL = 'https://github.com/astral-sh/python-build-standalone/releases/download/20261009/cpython-3.11.17%2B20261009-x86_64-pc-windows-msvc-install_only.tar.gz'
IMAGE_PYTHON_SHA256 = '4d307648d2fe5f8d927e10380cc33eb7afd8a34a7efe0ed786b5860b5f2d3408'
IMAGE_PYTHON_BYTES = 48233938


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    parser.add_argument('--python-archive', help='Explicit permitted public library cache; full pinned hash is rechecked')
    parser.add_argument('--image-python-archive', help='Explicit Astral CPython 3.11 archive cache for the isolated image adapter')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    if subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True).strip():
        raise SystemExit('Commit the reviewed source before building; source tree must be clean.')
    output = Path(args.output)
    if not output.is_absolute() or '..' in output.parts or output.exists():
        raise SystemExit('Use a new absolute build directory.')
    for part in (output, *output.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if part.is_symlink() or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise SystemExit('Reparse build paths are not supported.')
    output.mkdir()
    archive = output / 'cpython-install_only.tar.gz'
    if args.python_archive:
        cached = Path(args.python_archive)
        if not cached.is_absolute() or not cached.is_file():
            raise SystemExit('Use an explicit absolute public archive cache file.')
        shutil.copyfile(cached, archive)
    else:
        with urllib.request.urlopen(PYTHON_URL, timeout=120) as response, archive.open('xb') as target:
            shutil.copyfileobj(response, target, 1024 * 1024)
    if archive.stat().st_size != PYTHON_BYTES or digest(archive) != PYTHON_SHA256:
        raise SystemExit('Official CPython archive integrity failed; preserved for diagnosis.')
    extracted = output / 'python-source'
    extracted.mkdir()
    with tarfile.open(archive) as source:
        members = source.getmembers()
        for member in members:
            path = Path(member.name)
            if path.is_absolute() or '..' in path.parts or not (member.isfile() or member.isdir()):
                raise SystemExit('Unexpected archive component.')
        source.extractall(extracted, members=members)
    python_root = extracted / 'python'
    files = {p.relative_to(python_root).as_posix(): digest(p) for p in sorted(python_root.rglob('*')) if p.is_file()}
    metadata = {'implementation': 'CPython', 'version': '3.10.22', 'distribution': 'python-build-standalone', 'release': '20261009',
                'url': PYTHON_URL, 'archive_bytes': PYTHON_BYTES, 'archive_sha256': PYTHON_SHA256,
                'python_executable_sha256': digest(python_root / 'python.exe'), 'files': files,
                'support_note': 'Pinned for the existing Python 3.10 model runtime contract; no general maintenance support guarantee.'}
    resources = output / 'resources'
    resources.mkdir()
    (resources / 'python-runtime.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    image_archive=output/'cpython-image-install_only.tar.gz'
    if args.image_python_archive:
        cached=Path(args.image_python_archive)
        if not cached.is_absolute() or not cached.is_file():raise SystemExit('Use an explicit image Python archive file.')
        shutil.copyfile(cached,image_archive)
    else:
        with urllib.request.urlopen(IMAGE_PYTHON_URL,timeout=120) as response,image_archive.open('xb') as target:shutil.copyfileobj(response,target,1024*1024)
    if image_archive.stat().st_size!=IMAGE_PYTHON_BYTES or digest(image_archive)!=IMAGE_PYTHON_SHA256:raise SystemExit('Astral image CPython archive integrity failed; preserved.')
    image_extracted=output/'image-python-source';image_extracted.mkdir()
    with tarfile.open(image_archive) as source:
        members=source.getmembers()
        for member in members:
            path=Path(member.name)
            if path.is_absolute() or '..' in path.parts or not (member.isfile() or member.isdir()):raise SystemExit('Unexpected image Python archive component.')
        source.extractall(image_extracted,members=members)
    image_python_root=image_extracted/'python'
    image_files={p.relative_to(image_python_root).as_posix():digest(p) for p in sorted(image_python_root.rglob('*')) if p.is_file()}
    image_metadata=dict(implementation='CPython',version='3.11.17',distribution='Astral python-build-standalone',release='20261009',url=IMAGE_PYTHON_URL,archive_bytes=IMAGE_PYTHON_BYTES,archive_sha256=IMAGE_PYTHON_SHA256,python_executable_sha256=digest(image_python_root/'python.exe'),files=image_files)
    (resources/'python-image-runtime.json').write_text(json.dumps(image_metadata,indent=2),'utf8')
    entry = output / 'desktop_entry.py'
    entry.write_text('from ai_manager.desktop import main\nif __name__ == "__main__":\n    main()\n', encoding='utf-8')
    package_data = output / 'package-data/ai_manager'
    package_data.mkdir(parents=True)
    for original in [*sorted((root / 'src/ai_manager').glob('*.py')), *sorted((root / 'src/ai_manager').glob('model_manifest*.json')), *sorted((root / 'src/ai_manager').glob('adapter_manifest*.json')), *sorted((root / 'src/ai_manager').glob('requirements_*.lock'))]:
        shutil.copyfile(original, package_data / original.name)
    vendor = package_data / 'tapir_vendor'
    vendor.mkdir()
    for name in ('__init__.py','tapir_model.py','nets.py','utils.py','LICENSE','PROVENANCE.json'):
        shutil.copyfile(root/'src/ai_manager/tapir_vendor'/name, vendor/name)
    shutil.copytree(root / 'src/ai_manager/static', package_data / 'static')
    source_hashes = {'src/ai_manager/' + p.relative_to(package_data).as_posix(): digest(p) for p in sorted(package_data.rglob('*')) if p.is_file()}
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir', '--windowed', '--name', 'AiManager',
               '--distpath', str(output / 'dist'), '--workpath', str(output / 'work'), '--specpath', str(output),
               '--paths', str(package_data.parent), '--collect-all', 'webview', '--collect-all', 'pythonnet', '--collect-all', 'clr_loader',
               '--add-data', str(package_data) + ';ai_manager',
               '--add-data', str(python_root) + ';python_runtime',
               '--add-data', str(resources / 'python-runtime.json') + ';.',
               '--add-data', str(image_python_root) + ';python_image_runtime',
               '--add-data', str(resources / 'python-image-runtime.json') + ';.',
               '--add-data', str(root / 'requirements-runtime.lock') + ';.', str(entry)]
    subprocess.run(command, check=True)
    application = output / 'dist/AiManager'
    guidance = application / 'docs'
    guidance.mkdir()
    shutil.copyfile(root / 'docs/CANDIDATE_RANKING_INSTALL.md', guidance / 'CANDIDATE_RANKING_INSTALL.md')
    shutil.copyfile(root / 'docs/TYPOGRAPHY_LOCAL_0164.md', guidance / 'TYPOGRAPHY_LOCAL_0164.md')
    shutil.copyfile(root / 'docs/PREPARATION_READABILITY_0165.md', guidance / 'PREPARATION_READABILITY_0165.md')
    shutil.copyfile(root / 'docs/STARTUP_INVENTORY_READINESS.md', guidance / 'STARTUP_INVENTORY_READINESS.md')
    shutil.copyfile(root / 'docs/PERSONAL_MODEL_HUB_0170.md', guidance / 'PERSONAL_MODEL_HUB_0170.md')
    for lock in ('requirements.lock', 'requirements-desktop.lock', 'requirements-runtime.lock'):
        shutil.copyfile(root / lock, application / lock)
    notices = application / 'THIRD-PARTY-NOTICES.txt'
    notices.write_text('Ai Manager 0.17.0 Windows desktop\nCPython 3.10.22 python-build-standalone release 20261009\nSource: ' + PYTHON_URL +
                       '\nArchive SHA-256: ' + PYTHON_SHA256 + '\nCPython and bundled component licenses are preserved under _internal/python_runtime.\n'
                       'Python 3.10 is pinned for model compatibility; this is not a maintenance-support guarantee.\n'
                       'Host: PyInstaller 6.22.3, pywebview 6.2.1 (licenses preserved with package distribution metadata).\n'
                       'Microsoft Edge WebView2 Runtime is a separate prerequisite; no automatic system installation is performed.\n'
                       'TAPIR vendor source: google-deepmind/tapnet commit 730cda1c730877cfedbe01bf87fb1cadb78a565d, Apache-2.0; license and provenance are in ai_manager/tapir_vendor.\n', encoding='utf-8')
    with notices.open('a',encoding='utf8') as stream:stream.write('Image adapter base: Astral python-build-standalone CPython 3.11.17 release 20261009\nSource: '+IMAGE_PYTHON_URL+'\nArchive SHA-256: '+IMAGE_PYTHON_SHA256+'\nImage Python licenses are preserved under _internal/python_image_runtime.\n')
    license_dir = application / 'licenses'
    license_dir.mkdir()
    for name in ('pywebview', 'pyinstaller', 'pythonnet', 'clr_loader', 'pyinstaller-hooks-contrib', 'altgraph', 'bottle', 'cffi', 'packaging', 'pefile', 'proxy_tools', 'pycparser', 'pywin32-ctypes', 'setuptools', 'typing_extensions', 'wheel', 'requests', 'certifi', 'charset-normalizer', 'idna', 'urllib3'):
        distribution = importlib.metadata.distribution(name)
        for item in distribution.files or []:
            if any(term in item.name.casefold() for term in ('license', 'copying')):
                path = Path(distribution.locate_file(item))
                if path.is_file():
                    shutil.copyfile(path, license_dir / (name + '-' + item.name))
    provenance=dict(version='0.17.0',source_commit=source_commit,source_files=source_hashes,
        source_binding='PyInstaller uses package-data for imports and raw sources; frozen loader code is compared with compiled raw source before plan authority',
        imports='ai_manager.desktop',host='PyInstaller onedir / Edge WebView2',private_data_included=False)
    (application/'SOURCE-PROVENANCE.json').write_text(json.dumps(provenance,indent=2),encoding='utf8')
    manifest = {'version': '0.17.0', 'source_commit':source_commit,'python_runtime_archive_sha256': PYTHON_SHA256,
                'image_python_runtime_archive_sha256': IMAGE_PYTHON_SHA256,
                'build_environment': {'python': sys.version.split()[0], 'packages': {name: importlib.metadata.version(name) for name in ('pyinstaller', 'pywebview', 'pythonnet', 'clr_loader', 'pyinstaller-hooks-contrib', 'setuptools', 'wheel')}},
                'source_files': source_hashes,
                'files': {p.relative_to(application).as_posix(): digest(p) for p in sorted(application.rglob('*')) if p.is_file()}}
    (application / 'DESKTOP-MANIFEST.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    bundle = output / 'AiManager-0.17.0-windows.zip'
    with zipfile.ZipFile(bundle, 'x', zipfile.ZIP_DEFLATED) as target:
        for path in sorted(application.rglob('*')):
            if path.is_file():
                target.write(path, Path('AiManager') / path.relative_to(application))
    print(json.dumps({'status': 'built', 'zip_bytes': bundle.stat().st_size, 'zip_sha256': digest(bundle), 'exe_sha256': digest(application / 'AiManager.exe'), 'python_files': len(files)}))


if __name__ == '__main__':
    main()
