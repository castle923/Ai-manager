"""Fixed M12 CPU control probe, never a model executor."""
import json
import os
import sys
import time


def main():
    if len(sys.argv)!=4:return 2
    nonce,seconds,parent=sys.argv[1:]
    if len(nonce)!=32 or any(c not in '0123456789abcdef' for c in nonce):return 2
    try:seconds=int(seconds);parent=int(parent)
    except ValueError:return 2
    if not 0<=seconds<=30 or parent<=0:return 2
    print(json.dumps(dict(event='cpu_probe_started',nonce=nonce,pid=os.getpid(),model_test_performed=False)),flush=True)
    start=time.monotonic()
    while time.monotonic()-start<seconds:
        # POSIX orphan probes self-stop; Windows parent uses kill-on-close Job ownership.
        if os.name!='nt' and os.getppid()!=parent:return 3
        time.sleep(.02)
    print(json.dumps(dict(event='cpu_probe_finished',nonce=nonce,pid=os.getpid(),model_test_performed=False)),flush=True)
    return 0


if __name__=='__main__':sys.exit(main())
