"""Stage only the fixed public Colab sources for wheel and desktop builds."""
import hashlib
import json
import os
from pathlib import Path
import stat

PUBLIC_FILES = (
    'src/ai_manager/colab_contract.py',
    'src/ai_manager/colab_source_pins.json',
    'src/ai_manager/adapter_manifest_llama.json',
    'scripts/colab/build_llama_handoff.py',
    'scripts/colab/llama_handoff_worker.py',
    'scripts/colab/llama_watchdog.py',
)


def check_path(path):
    for part in (*reversed(path.parents), path):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('unsafe_public_resource_path')


def stage(repository, package):
    repository, package = (Path(os.path.abspath(value)) for value in (repository, package))
    check_path(repository)
    check_path(package)
    public = package / 'colab_public'
    contents = {}
    for relative in PUBLIC_FILES:
        source = repository / relative
        check_path(source)
        contents[relative] = source.read_bytes()
    raw_pins = contents['src/ai_manager/colab_source_pins.json']
    pins = json.loads(raw_pins)
    for role, relative in zip(('contract', 'worker', 'guard'),
                              (PUBLIC_FILES[0], PUBLIC_FILES[4], PUBLIC_FILES[5])):
        if hashlib.sha256(contents[relative]).hexdigest() != pins[role]:
            raise ValueError('source_mismatch')
    installed_pins = package / 'colab_source_pins.json'
    check_path(installed_pins)
    if installed_pins.exists() and installed_pins.read_bytes() != raw_pins:
        raise FileExistsError('public_resource_pins_conflict')
    if public.exists():
        check_path(public)
        actual = set()
        for item in public.rglob('*'):
            check_path(item)
            if item.is_file():
                actual.add(item.relative_to(public).as_posix())
        if actual != set(contents) or not installed_pins.is_file():
            raise FileExistsError('public_resource_destination_conflict')
        for relative, raw in contents.items():
            if (public / relative).read_bytes() != raw:
                raise FileExistsError('public_resource_destination_conflict')
        return [installed_pins, *(public / relative for relative in PUBLIC_FILES)]
    public.mkdir(parents=True)
    for relative, raw in contents.items():
        target = public / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as output:
            output.write(raw)
    if not installed_pins.exists():
        with installed_pins.open('xb') as output:
            output.write(raw_pins)
    return [installed_pins, *(public / relative for relative in PUBLIC_FILES)]
