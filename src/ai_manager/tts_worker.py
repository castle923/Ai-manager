"""One cold, offline, approved Qwen CustomVoice invocation. No arbitrary code."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import time
import uuid


def write(path, value):
    temporary = path.with_name(uuid.uuid4().hex + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf8')
    for attempt in range(40):
        try:
            os.replace(temporary, path); return
        except PermissionError:
            if attempt == 39: raise
            time.sleep(.05)


def publish_audio(directory, audio, rate, sf):
    temporary = directory / (uuid.uuid4().hex + '.partial.wav')
    sf.write(str(temporary), audio, rate, subtype='PCM_16', format='WAV')
    info = sf.info(str(temporary))
    if info.frames != audio.size or info.samplerate != rate or info.channels != 1 or info.subtype != 'PCM_16':
        raise ValueError('output_invalid')
    # Same-volume hard link publishes all bytes atomically and refuses to
    # replace an existing output. A failed attempt preserves its partial.
    os.link(temporary, directory / 'output.wav')
    temporary.unlink()


def completion_metrics(value, torch, eos):
    codes = torch.stack([hid[-1] for hid in value.hidden_states if hid[-1] is not None], dim=1)
    tokens = value.sequences.shape[-1]
    # HF hidden states describe the preceding forward pass: the last sampled
    # EOS may be present only in sequences, not hidden codes.
    return dict(generated_codec_frames=codes.shape[1], generated_sequence_tokens=tokens,
                eos_reached=bool(tokens > 0 and (value.sequences[:, -1] == eos).all().item()))


def main():
    request_path = Path(sys.argv[1]); directory = request_path.parent
    request = json.loads(request_path.read_text(encoding='utf8'))
    run_id = request['run_id']; text = request['text']
    result = dict(run_id=run_id, input_sha256=hashlib.sha256(text.encode('utf8')).hexdigest(), status='failed')
    def phase(status): write(directory / 'progress.json', dict(run_id=run_id, status=status))
    try:
        # Offline flags are inherited before importing Hugging Face or torch.
        import torch
        import numpy as np
        import soundfile as sf
        from qwen_tts import Qwen3TTSModel
        if not torch.cuda.is_available():
            result['error'] = 'runtime_not_ready'; raise RuntimeError()
        parameters=request['parameters']
        sampling=dict(do_sample=True, top_k=50, top_p=1.0, temperature=0.9, repetition_penalty=1.05, subtalker_dosample=True, subtalker_top_k=50, subtalker_top_p=1.0, subtalker_temperature=0.9)
        if parameters.get('sampling') != sampling:
            result['error']='inference_failed';raise ValueError('unsupported_sampling_parameters')
        if parameters['language'] != 'Korean' or parameters['speaker'] != 'Sohee' or parameters['batch_size'] != 1 or parameters['instruct'] is not None or parameters['max_new_tokens'] != 1024:
            result['error']='inference_failed';raise ValueError('unsupported_parameters')
        torch.manual_seed(parameters['seed'])
        torch.cuda.reset_peak_memory_stats()
        phase('loading'); start = time.monotonic()
        model = Qwen3TTSModel.from_pretrained(request['model_path'], device_map='cuda:0', dtype=torch.bfloat16,
                                             attn_implementation='sdpa', local_files_only=True, trust_remote_code=False)
        torch.cuda.synchronize(); loading = time.monotonic() - start
        phase('running'); start = time.monotonic()
        completion = {}
        original_generate = model.model.talker.generate
        def tracked_generate(*args, **kwargs):
            value = original_generate(*args, **kwargs)
            eos = model.model.config.talker_config.codec_eos_token_id
            completion.update(completion_metrics(value, torch, eos))
            return value
        model.model.talker.generate = tracked_generate
        with torch.inference_mode():
            wavs, rate = model.generate_custom_voice(text=text, language=parameters['language'], speaker=parameters['speaker'],
                                                      max_new_tokens=parameters['max_new_tokens'], **sampling)
        torch.cuda.synchronize(); inference = time.monotonic() - start
        phase('validating')
        if not completion.get('eos_reached'):
            result['metrics'] = dict(loading_seconds=round(loading, 3), inference_seconds=round(inference, 3), **completion)
            result['error'] = 'generation_limit_reached'; raise RuntimeError()
        if len(wavs) != 1 or rate != 24000:
            result['error'] = 'output_invalid'; raise RuntimeError()
        audio = np.asarray(wavs[0])
        if audio.ndim != 1 or audio.size == 0 or not np.isfinite(audio).all() or float(np.max(np.abs(audio))) > 1:
            result['error'] = 'output_invalid'; raise RuntimeError()
        try:
            publish_audio(directory, audio, rate, sf)
        except (OSError, ValueError):
            result['error'] = 'output_invalid'; raise
        result.update(status='generated', metrics=dict(loading_seconds=round(loading, 3), inference_seconds=round(inference, 3),
                      peak_gpu_allocated_bytes=torch.cuda.max_memory_allocated(), device=torch.cuda.get_device_name(0),
                      cold_loading=True, dtype='bfloat16', attention='sdpa', seed=request['parameters']['seed'],
                      **completion,
                      packages={name: importlib.metadata.version(name) for name in ('qwen-tts', 'torch', 'transformers', 'soundfile')}))
    except Exception as error:
        result.setdefault('error', 'inference_out_of_memory' if type(error).__name__ in {'OutOfMemoryError', 'CUDAOutOfMemoryError'} else 'inference_failed')
        # Private worker logs contain diagnostic stacks; public status only has codes.
        import traceback
        traceback.print_exc()
    write(directory / 'result.json', result)
    return 0 if result['status'] == 'generated' else 1


if __name__ == '__main__':
    raise SystemExit(main())
