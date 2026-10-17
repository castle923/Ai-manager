"""Per-workspace display preferences, separate from credentials and Drive scope."""
import json
import os
from pathlib import Path
import threading
import uuid

from .config import private_home
from .inference import FileOwner


DEFAULTS = dict(default_section='registry', history_page_size=25, time_display='local', memory_unit='GiB')
CHOICES = dict(default_section={'registry','history'}, history_page_size={10,25,50}, time_display={'local','UTC'}, memory_unit={'MiB','GiB'})


class PreferenceError(ValueError):
    pass


class Preferences:
    def __init__(self, home):
        self.home=private_home(home)
        self.path=self.home/'preferences.json'
        self.lock=threading.RLock()

    @staticmethod
    def validate(value):
        if not isinstance(value,dict) or set(value)!=set(DEFAULTS): raise PreferenceError('preferences_invalid')
        for key,choices in CHOICES.items():
            if type(value[key]) is not type(DEFAULTS[key]) or value[key] not in choices: raise PreferenceError('preferences_invalid')
        return dict(value)

    def read(self):
        try:
            path=private_home(self.path)
            if not path.exists(): return dict(schema_version=1,revision=0,values=dict(DEFAULTS),persisted=False)
            if path.stat().st_size>4096: raise PreferenceError('preferences_invalid')
            record=json.loads(path.read_text(encoding='utf8'))
            if not isinstance(record,dict) or set(record)!={'schema_version','revision','values'} or type(record['schema_version'])is not int or record['schema_version']!=1 or type(record['revision'])is not int or not 1<=record['revision']<=2**53-1: raise PreferenceError('preferences_invalid')
            self.validate(record['values'])
            return dict(record,persisted=True)
        except (OSError,ValueError,TypeError) as error:
            if isinstance(error,PreferenceError):raise
            raise PreferenceError('preferences_unavailable') from None

    def update(self, data):
        if not isinstance(data,dict) or set(data)!={'revision','values'} or type(data['revision'])is not int or not 0<=data['revision']<2**53-1: raise PreferenceError('preferences_invalid')
        values=self.validate(data['values'])
        with self.lock:
            owner=None;temporary=None
            try:
                lock_path=private_home(self.home/'preferences-owner.lock')
                owner=FileOwner(lock_path)
                if not owner.handle: raise PreferenceError('preferences_busy')
                old=self.read()
                if old['revision']!=data['revision']: raise PreferenceError('preferences_stale')
                record=dict(schema_version=1,revision=old['revision']+1,values=values)
                temporary=private_home(self.home/('preferences-'+uuid.uuid4().hex+'.tmp'))
                with temporary.open('x',encoding='utf8')as handle:
                    json.dump(record,handle,ensure_ascii=False,indent=2);handle.flush();os.fsync(handle.fileno())
                private_home(self.path)
                os.replace(temporary,self.path)
                return self.read()
            except OSError:
                raise PreferenceError('preferences_unavailable') from None
            finally:
                if temporary is not None and temporary.is_file():temporary.unlink()
                if owner is not None:owner.close()
