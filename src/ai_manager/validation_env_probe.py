"""Fixed read-only runtime/resource observation; never loads a model."""
import importlib.metadata
import json
import shutil
import sys


def main():
    import torch
    import ctypes
    import os
    from ctypes import wintypes
    class Memory(ctypes.Structure):
        _fields_=[('length',wintypes.DWORD),('load',wintypes.DWORD)]+[(name,ctypes.c_ulonglong) for name in ('total_physical','available_physical','total_pagefile','available_pagefile','total_virtual','available_virtual','available_extended_virtual')]
    memory=Memory();memory.length=ctypes.sizeof(memory)
    if os.name!='nt' or not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):raise ValueError('resource_observation_unavailable')
    packages={}
    for name in json.loads(sys.argv[1]):
        if name in ('diffusers_git_revision','pipeline_source_sha256'):continue
        packages[name]=importlib.metadata.version(name)
    if 'diffusers_git_revision' in json.loads(sys.argv[1]):
        import hashlib
        from pathlib import Path
        import diffusers
        direct=json.loads(importlib.metadata.distribution('diffusers').read_text('direct_url.json'))
        packages['diffusers_git_revision']=direct['vcs_info']['commit_id']
        packages['pipeline_source_sha256']=hashlib.sha256((Path(diffusers.__file__).parent/'pipelines/qwenimage21/pipeline_qwenimage21.py').read_bytes()).hexdigest()
    available=torch.cuda.is_available()
    free,total=torch.cuda.mem_get_info(0) if available else (0,0)
    print(json.dumps(dict(python=sys.version.split()[0],packages=packages,cuda_available=available,
        gpu_free_bytes=free,gpu_total_bytes=total,ram_available_bytes=memory.available_physical,
        cpu_count=os.cpu_count(),disk_free_bytes=shutil.disk_usage(sys.argv[2]).free)))


if __name__=='__main__':main()
