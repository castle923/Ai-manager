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
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
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
    entry = output / 'desktop_entry.py'
    entry.write_text('from ai_manager.desktop import main\nif __name__ == "__main__":\n    main()\n', encoding='utf-8')
    package_data = output / 'package-data/ai_manager'
    package_data.mkdir(parents=True)
    for original in [*sorted((root / 'src/ai_manager').glob('*.py')), *sorted((root / 'src/ai_manager').glob('model_manifest*.json'))]:
        shutil.copyfile(original, package_data / original.name)
    shutil.copytree(root / 'src/ai_manager/static', package_data / 'static')
    source_hashes = {'src/ai_manager/' + p.relative_to(package_data).as_posix(): digest(p) for p in sorted(package_data.rglob('*')) if p.is_file()}
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir', '--windowed', '--name', 'AiManager',
               '--distpath', str(output / 'dist'), '--workpath', str(output / 'work'), '--specpath', str(output),
               '--paths', str(package_data.parent), '--collect-all', 'webview', '--collect-all', 'pythonnet', '--collect-all', 'clr_loader',
               '--add-data', str(package_data) + ';ai_manager',
               '--add-data', str(python_root) + ';python_runtime',
               '--add-data', str(resources / 'python-runtime.json') + ';.',
               '--add-data', str(root / 'requirements-runtime.lock') + ';.', str(entry)]
    subprocess.run(command, check=True)
    application = output / 'dist/AiManager'
    guidance = application / 'docs'
    guidance.mkdir()
    shutil.copyfile(root / 'docs/M9_INSTALL.md', guidance / 'M9_INSTALL.md')
    for lock in ('requirements.lock', 'requirements-desktop.lock', 'requirements-runtime.lock'):
        shutil.copyfile(root / lock, application / lock)
    notices = application / 'THIRD-PARTY-NOTICES.txt'
    notices.write_text('Ai-manager 0.9.0 Windows desktop\nCPython 3.10.22 python-build-standalone release 20261009\nSource: ' + PYTHON_URL +
                       '\nArchive SHA-256: ' + PYTHON_SHA256 + '\nCPython and bundled component licenses are preserved under _internal/python_runtime.\n'
                       'Python 3.10 is pinned for model compatibility; this is not a maintenance-support guarantee.\n'
                       'Host: PyInstaller 6.22.3, pywebview 6.2.1 (licenses preserved with package distribution metadata).\n'
                       'Microsoft Edge WebView2 Runtime is a separate prerequisite; no automatic system installation is performed.\n', encoding='utf-8')
    license_dir = application / 'licenses'
    license_dir.mkdir()
    for name in ('pywebview', 'pyinstaller', 'pythonnet', 'clr_loader', 'pyinstaller-hooks-contrib', 'altgraph', 'bottle', 'cffi', 'packaging', 'pefile', 'proxy_tools', 'pycparser', 'pywin32-ctypes', 'setuptools', 'typing_extensions', 'wheel', 'requests', 'certifi', 'charset-normalizer', 'idna', 'urllib3'):
        distribution = importlib.metadata.distribution(name)
        for item in distribution.files or []:
            if any(term in item.name.casefold() for term in ('license', 'copying')):
                path = Path(distribution.locate_file(item))
                if path.is_file():
                    shutil.copyfile(path, license_dir / (name + '-' + item.name))
    manifest = {'version': '0.9.0', 'python_runtime_archive_sha256': PYTHON_SHA256,
                'build_environment': {'python': sys.version.split()[0], 'packages': {name: importlib.metadata.version(name) for name in ('pyinstaller', 'pywebview', 'pythonnet', 'clr_loader', 'pyinstaller-hooks-contrib', 'setuptools', 'wheel')}},
                'source_files': source_hashes,
                'files': {p.relative_to(application).as_posix(): digest(p) for p in sorted(application.rglob('*')) if p.is_file()}}
    (application / 'DESKTOP-MANIFEST.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    bundle = output / 'AiManager-0.9.0-windows.zip'
    with zipfile.ZipFile(bundle, 'x', zipfile.ZIP_DEFLATED) as target:
        for path in sorted(application.rglob('*')):
            if path.is_file():
                target.write(path, Path('AiManager') / path.relative_to(application))
    print(json.dumps({'status': 'built', 'zip_bytes': bundle.stat().st_size, 'zip_sha256': digest(bundle), 'exe_sha256': digest(application / 'AiManager.exe'), 'python_files': len(files)}))


if __name__ == '__main__':
    main()
