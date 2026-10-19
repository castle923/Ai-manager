"""Cooperative single-worker admission within one app home, across TTS/task owners."""
from pathlib import Path


def acquire(home, check_cancel, closed):
    from .inference import FileOwner, regular
    path = regular(Path(home) / 'execution-slot.lock', Path(home))
    while True:
        check_cancel()
        owner = FileOwner(path)
        if owner.handle:
            return owner
        closed.wait(.15)
