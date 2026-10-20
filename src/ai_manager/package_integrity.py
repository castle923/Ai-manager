"""Verify frozen imports against the raw source from the same recorded build."""
import hashlib
import importlib.util
import json
import marshal
from pathlib import Path
import sys
import types


def _normalized(code):
    return code.replace(co_filename='<bound-source>',co_consts=tuple(_normalized(v) if isinstance(v,types.CodeType) else v for v in code.co_consts))


def verify_frozen(*,full=False):
    if not getattr(sys,'frozen',False):return None
    from .validation_contracts import fail,ContractError
    root=Path(sys.executable).parent
    try:
        manifest=json.loads((root/'DESKTOP-MANIFEST.json').read_text('utf8'))
        provenance=json.loads((root/'SOURCE-PROVENANCE.json').read_text('utf8'))
        if manifest['version']!='0.16.6' or provenance['version']!='0.16.6' or manifest['source_files']!=provenance['source_files']:fail('package_source_manifest_mismatch')
        if len(provenance['source_commit'])!=40 or not provenance['source_files']:fail('package_source_provenance_invalid')
        package=Path(__file__).parent
        for relative,expected in provenance['source_files'].items():
            if not relative.startswith('src/ai_manager/'):fail('package_source_path_invalid')
            path=package/relative.removeprefix('src/ai_manager/')
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:fail('package_source_integrity_failed')
            if path.suffix=='.py':
                parts=path.relative_to(package).with_suffix('').parts
                name='ai_manager'+('' if parts==('__init__',) else '.'+'.'.join(parts[:-1] if parts[-1]=='__init__' else parts))
                spec=importlib.util.find_spec(name)
                if spec is None or not hasattr(spec.loader,'get_code'):fail('package_import_unverifiable')
                loaded=spec.loader.get_code(name)
                compiled=compile(path.read_bytes(),'<bound-source>','exec',dont_inherit=True,optimize=sys.flags.optimize)
                if _normalized(loaded)!=_normalized(compiled):fail('package_import_source_mismatch')
        required=[Path(sys.executable).name,'SOURCE-PROVENANCE.json']
        paths=manifest['files'] if full else {k:manifest['files'][k] for k in required}
        for relative,expected in paths.items():
            path=root/relative
            if not path.is_relative_to(root) or '..' in Path(relative).parts or not path.is_file():fail('package_file_missing')
            value=hashlib.sha256()
            with path.open('rb') as stream:
                for chunk in iter(lambda:stream.read(1048576),b''):value.update(chunk)
            if value.hexdigest()!=expected:fail('package_integrity_failed')
        return provenance
    except ContractError:raise
    except (OSError,ValueError,KeyError,TypeError,AttributeError,ImportError):fail('package_integrity_unavailable')
