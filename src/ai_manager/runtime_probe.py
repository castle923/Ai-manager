"""Offline dependency/device probe; never loads a model or produces inference."""
import contextlib
import io
import importlib.metadata
import json
import platform
import shutil

def main():
    result=dict(python=platform.python_version(),packages={},cuda_available=False,device=None,blockers=[])
    for name in ('qwen-tts','torch','torchaudio','transformers','accelerate','soundfile','onnxruntime','sox'):
        try:result['packages'][name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:result['blockers'].append('runtime_dependency_missing')
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            import torch
            import torchaudio
            import soundfile
            import qwen_tts
            import transformers
            import accelerate
            import onnxruntime
            import sox
        result['cuda_available']=torch.cuda.is_available()
        if result['cuda_available']:result['device']=torch.cuda.get_device_name(0)
        else:result['blockers'].append('cuda_unavailable')
    except Exception:result['blockers'].append('runtime_import_failed')
    result['blockers']=sorted(set(result['blockers']))
    result['sox_binary_available']=bool(shutil.which('sox'))
    result['model_loaded']=False
    result['inference_performed']=False
    result['status']='blocked' if result['blockers'] else 'ready'
    print(json.dumps(result))
if __name__=='__main__':main()
