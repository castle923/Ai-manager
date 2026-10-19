"""Import-only tracking readiness probe; never loads weights or runs inference."""
import importlib.metadata
import json
import sys
from pathlib import Path

try:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import torch
    import av
    from ai_manager.tapir_vendor.tapir_model import TAPIR
    print(json.dumps(dict(status='ready' if torch.cuda.is_available() else 'cuda_unavailable',
        cuda_available=torch.cuda.is_available(), packages={name: importlib.metadata.version(name)
        for name in ('torch', 'numpy', 'Pillow', 'av', 'dm-tree', 'einshape')})))
except Exception:
    print(json.dumps(dict(status='unavailable')))
    raise SystemExit(1)
