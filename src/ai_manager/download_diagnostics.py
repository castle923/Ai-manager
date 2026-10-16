"""Opt-in, bounded private diagnostics for audio transport; never request content."""
import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit


class DownloadDiagnostics:
    def __init__(self, home, enabled=False):
        self.enabled = enabled
        self.session_id = uuid.uuid4().hex if enabled else None
        self.path = None
        self.failed = False
        self.count = 0
        self.lock = threading.Lock()
        if enabled:
            try:
                folder = Path(home) / 'diagnostics' / self.session_id
                folder.mkdir(parents=True, exist_ok=False)
                self.path = folder / 'audio-transport.jsonl'
                self.path.touch(exist_ok=False)
            except OSError:
                self.failed = True

    def health(self):
        return {'enabled': self.enabled, 'healthy': self.enabled and not self.failed and self.count < 1000,
                'session_id': self.session_id, 'records_written': self.count}

    def begin(self, method, target):
        path = urlsplit(target).path
        route = 'audio' if re.fullmatch(r'/api/tts/runs/[a-f0-9]{32}/audio', path) else 'diagnostics_health' if path == '/api/diagnostics/health' else None
        if not self.enabled or method != 'GET' or route is None:
            return None
        context = {'request_id': uuid.uuid4().hex, 'method': 'GET', 'route': route}
        self.record(context, 'request_received')
        return context

    def record(self, context, stage, *, status=None, mime=None, download=None, content_length=None, bytes_written=None, error_stage=None):
        if not context or not self.enabled:
            return
        # All fields are generated or allowlisted, never raw request/exception values.
        item = {**context, 'time_utc': datetime.now(timezone.utc).isoformat(), 'stage': stage}
        if status is not None: item['status'] = int(status)
        if mime is not None: item['mime'] = mime if mime in {'audio/wav', 'application/json; charset=utf-8'} else 'other'
        if download is not None:
            item['content_disposition'] = 'attachment'
            item['filename'] = download if re.fullmatch(r'[a-f0-9]{32}\.wav', download) else '[redacted]'
        if content_length is not None: item['content_length'] = int(content_length)
        if bytes_written is not None: item['bytes_written'] = int(bytes_written)
        if error_stage is not None: item['error_stage'] = error_stage
        try:
            with self.lock:
                if self.failed or self.count >= 1000: return
                with self.path.open('a', encoding='utf-8') as stream:
                    stream.write(json.dumps(item, separators=(',', ':')) + '\n')
                    stream.flush()
                self.count += 1
        except (OSError, ValueError):
            self.failed = True
