"""One local-only Whisper transcription; fixed Korean, greedy bounded generation."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import time
import uuid
import wave


def write(path,value):
    temporary=path.with_name(uuid.uuid4().hex+'.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2),'utf8')
    os.replace(temporary,path)


def main():
    directory=Path(sys.argv[1]).parent
    request=json.loads(Path(sys.argv[1]).read_text('utf8'))
    result=dict(run_id=request['run_id'],input_sha256=request['input_sha256'],status='failed')
    def phase(value):write(directory/'progress.json',dict(run_id=request['run_id'],status=value))
    try:
        import torch
        import numpy as np
        from transformers import WhisperProcessor, WhisperForConditionalGeneration
        if not torch.cuda.is_available(): raise ValueError('adapter_runtime_not_ready')
        audio_path=directory/'input.wav'
        if hashlib.sha256(audio_path.read_bytes()).hexdigest()!=request['input_sha256']: raise ValueError('input_changed')
        with wave.open(str(audio_path),'rb') as reader:
            if reader.getframerate()!=16000 or reader.getnchannels()!=1 or reader.getsampwidth()!=2 or not 0<reader.getnframes()<=480000: raise ValueError('input_audio_invalid')
            samples=np.frombuffer(reader.readframes(reader.getnframes()),dtype='<i2').astype(np.float32)/32768
        torch.manual_seed(0);torch.cuda.reset_peak_memory_stats()
        phase('loading'); start=time.monotonic()
        processor=WhisperProcessor.from_pretrained(request['model_path'],local_files_only=True,trust_remote_code=False)
        model=WhisperForConditionalGeneration.from_pretrained(request['model_path'],local_files_only=True,trust_remote_code=False,torch_dtype=torch.float16,use_safetensors=True).to('cuda').eval()
        torch.cuda.synchronize(); loading=time.monotonic()-start
        phase('running');start=time.monotonic()
        features=processor(samples,sampling_rate=16000,return_tensors='pt').input_features.to('cuda',dtype=torch.float16)
        with torch.inference_mode():
            tokens=model.generate(features,language='ko',task='transcribe',do_sample=False,max_new_tokens=256,return_timestamps=False)
        torch.cuda.synchronize();elapsed=time.monotonic()-start
        if tokens.shape[-1]>=256 and tokens[0,-1].item()!=model.generation_config.eos_token_id: raise ValueError('generation_limit_reached')
        text=processor.batch_decode(tokens,skip_special_tokens=True)[0].strip()
        if not text: raise ValueError('output_invalid')
        phase('validating')
        value=dict(text=text,language='ko',input_duration_seconds=len(samples)/16000,timestamps=None)
        for name,data in [('transcript.json',json.dumps(value,ensure_ascii=False,indent=2).encode('utf8')),('transcript.txt',text.encode('utf8'))]:
            temporary=directory/(uuid.uuid4().hex+'.partial')
            temporary.write_bytes(data);os.link(temporary,directory/name);temporary.unlink()
        result.update(status='generated',metrics=dict(loading_seconds=round(loading,3),inference_seconds=round(elapsed,3),peak_gpu_allocated_bytes=torch.cuda.max_memory_allocated(),cold_loading=True,dtype='float16',seed=0,device=torch.cuda.get_device_name(0),packages={name:importlib.metadata.version(name) for name in ('torch','transformers','numpy','safetensors','tokenizers')}))
    except Exception as error:
        code=str(error)
        result['error']=code if code in {'generation_limit_reached','input_changed','input_audio_invalid','output_invalid','adapter_runtime_not_ready'} else 'inference_out_of_memory' if type(error).__name__ in {'OutOfMemoryError','CUDAOutOfMemoryError'} else 'inference_failed'
        import traceback;traceback.print_exc()
    write(directory/'result.json',result)
    return 0 if result['status']=='generated' else 1

def entrypoint():
    try:
        return main()
    except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError):
        # Malformed private request data must not escape as an uncontrolled stack.
        if len(sys.argv) == 2:
            directory = Path(sys.argv[1]).parent
            try:
                write(directory / 'result.json', dict(run_id=directory.name, input_sha256='', status='failed', error='request_invalid'))
            except OSError:
                pass
        return 1


if __name__ == '__main__':
    raise SystemExit(entrypoint())
