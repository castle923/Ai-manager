"""Explicit local workspace mode, without OAuth inputs or credential storage."""
from .auth import AuthError


def is_local(settings):
    return settings.get('mode') == 'local'


class NoDriveAuth:
    """No store/session/browser exists in this mode; remote calls fail closed."""
    def denied(self, *args, **kwargs):
        raise AuthError('drive_setup_required')

    connect = access = disconnect = denied


def account_status(settings, auth):
    if is_local(settings):
        return {}
    return {a: {'credential_saved': bool(auth.store.get(a)),
                'roots': sum(r['account'] == a for r in settings['allowlist'])}
            for a in ('A', 'B')}


def drive_status(settings):
    return {'configuration': 'not_configured' if is_local(settings) else 'configured',
            'mode': 'local' if is_local(settings) else 'drive'}
