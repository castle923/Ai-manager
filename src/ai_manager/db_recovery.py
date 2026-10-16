"""Explicit SQLite backup/restore into a new target; never replace user data."""
from contextlib import closing
import hashlib
import os
from pathlib import Path
import sqlite3
import time
import uuid
from .inference import regular
from .inventory import SCHEMA_SQL

REQUIRED = {
    'scans': {'scan_id','account','settings_version','settings_json','started_at','finished_at','status','pid','files_count','folders_count','excluded_count','pages_count','errors_json'},
    'files': {'scan_id','file_id','root_alias','path','kind','metadata_json'},
}


def _check(connection):
    if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
        raise ValueError('database_integrity_failed')
    tables={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if tables != set(REQUIRED): raise ValueError('database_schema_unsupported')
    if connection.execute("SELECT count(*) FROM sqlite_master WHERE type IN ('trigger','view')").fetchone()[0]:
        raise ValueError('database_schema_unsupported')
    for table, columns in REQUIRED.items():
        if {r[1] for r in connection.execute('PRAGMA table_info('+table+')')} != columns:
            raise ValueError('database_schema_unsupported')
    if connection.execute('PRAGMA foreign_key_check').fetchone() is not None:
        raise ValueError('database_integrity_failed')
    def schema(conn):
        return [(kind,name,sql.strip()) for kind,name,sql in conn.execute("SELECT type,name,sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type,name")]
    with closing(sqlite3.connect(':memory:')) as canonical:
        canonical.executescript(SCHEMA_SQL)
        if schema(connection) != schema(canonical):
            raise ValueError('database_schema_unsupported')


def copy_database_to_new_target(source, destination):
    source, destination=Path(source),Path(destination)
    if not source.is_absolute() or not destination.is_absolute() or '..' in source.parts or '..' in destination.parts: raise ValueError('absolute_database_paths_required')
    regular(source,Path(source.anchor)); regular(destination,Path(destination.anchor))
    if not source.is_file(): raise ValueError('database_source_missing')
    if destination.exists(): raise ValueError('database_destination_exists')
    destination.parent.mkdir(parents=True,exist_ok=True)
    temporary=destination.parent/(uuid.uuid4().hex+'.sqlite3.tmp')
    # Exclusive creation and final no-replace publication prevent accidental overwrite.
    with temporary.open('xb'): pass
    try:
        with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True,timeout=10)) as incoming:
            incoming.execute('PRAGMA query_only=ON'); incoming.execute('PRAGMA busy_timeout=250'); _check(incoming)
            with closing(sqlite3.connect(temporary,timeout=10)) as outgoing:
                outgoing.execute('PRAGMA busy_timeout=250')
                deadline = time.monotonic() + 10
                def progress(status, remaining, total):
                    if time.monotonic() >= deadline:
                        raise ValueError('database_backup_timeout')
                incoming.backup(outgoing, pages=128, progress=progress, sleep=0.05)
                _check(outgoing)
        with temporary.open('r+b') as stream: os.fsync(stream.fileno())
        regular(destination,Path(destination.anchor))
        os.link(temporary,destination); temporary.unlink()
    except sqlite3.DatabaseError:
        raise ValueError('database_unreadable_or_corrupt') from None
    # Failed temporary artifacts are preserved; the original and existing target are never removed.
    return {'status':'copied_to_new_target','integrity':'ok','schema':'supported','bytes':destination.stat().st_size,'sha256':hashlib.sha256(destination.read_bytes()).hexdigest()}
