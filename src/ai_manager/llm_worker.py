"""One offline, bounded Llama chat generation in a parent-owned subprocess.

The parent verifies the exact manifest directory and kills the process on its
wall-clock timeout or cancellation. Accelerate max_memory is a placement budget,
not an OS process RAM quota; disk offload may be necessary for this 8B model.
"""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import sys
import time
import uuid


PARAMETERS = dict(max_new_tokens=64, max_input_tokens=256, seed=0, do_sample=False)
ERRORS = {'request_invalid', 'input_changed', 'input_text_invalid',
          'input_token_limit', 'model_invalid', 'output_invalid',
          'generation_timeout', 'adapter_runtime_not_ready', 'output_exists','memory_budget_unavailable'}


def write(path, value):
    temporary = path.with_name(uuid.uuid4().hex + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), 'utf8')
    os.replace(temporary, path)


def publish(path, data):
    """Publish without replacing a previous run artifact."""
    temporary = path.with_name(uuid.uuid4().hex + '.partial')
    try:
        temporary.write_bytes(data)
        os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def validate_request(request, directory):
    if (not isinstance(request, dict) or
            not isinstance(request.get('run_id'), str) or
            not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', request['run_id']) or
            request.get('parameters') != PARAMETERS or
            any(type(request['parameters'].get(k)) is not type(v) for k, v in PARAMETERS.items())):
        raise ValueError('request_invalid')
    expected = request.get('input_sha256')
    metadata = request.get('input_metadata')
    if (not isinstance(expected, str) or not re.fullmatch('[0-9a-f]{64}', expected)
            or not isinstance(metadata, dict) or metadata.get('sha256') != expected
            or type(metadata.get('bytes')) is not int or not 0 < metadata['bytes'] <= 8192):
        raise ValueError('request_invalid')
    path = directory / 'input.txt'
    if path.is_symlink() or not path.is_file():
        raise ValueError('input_text_invalid')
    with path.open('rb') as reader:
        data = reader.read(8193)
    if len(data) != metadata['bytes'] or hashlib.sha256(data).hexdigest() != expected:
        raise ValueError('input_changed')
    try:
        text = data.decode('utf8')
    except UnicodeDecodeError:
        raise ValueError('input_text_invalid') from None
    if not text.strip() or '\x00' in text:
        raise ValueError('input_text_invalid')
    if any((directory / name).exists() for name in ('response.json', 'response.txt', 'offload')):
        raise ValueError('output_exists')
    return text


def validate_model(value):
    if not isinstance(value, str) or not Path(value).is_absolute():
        raise ValueError('model_invalid')
    root = Path(value)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('model_invalid')
    try:
        config = json.loads((root / 'config.json').read_text('utf8'))
        tokenizer = json.loads((root / 'tokenizer_config.json').read_text('utf8'))
        index = json.loads((root / 'model.safetensors.index.json').read_text('utf8'))
        names = set(index['weight_map'].values())
        if (config.get('model_type') != 'llama' or
                config.get('architectures') != ['LlamaForCausalLM'] or
                config.get('auto_map') or tokenizer.get('auto_map') or not names):
            raise ValueError()
        for name in names:
            if not isinstance(name, str) or not re.fullmatch(r'model-\d{5}-of-\d{5}\.safetensors', name):
                raise ValueError()
        for name in names | {'config.json', 'tokenizer_config.json', 'tokenizer.json', 'model.safetensors.index.json'}:
            path = root / name
            if path.is_symlink() or not path.is_file():
                raise ValueError()
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        raise ValueError('model_invalid') from None
    return root


def finish_reason(ids, eos_ids, maximum=64):
    if not ids or len(ids) > maximum:
        raise ValueError('output_invalid')
    if ids[-1] in eos_ids:
        return 'eos'
    if len(ids) == maximum:
        return 'length'
    raise ValueError('generation_timeout')


def generate(request, directory, phase):
    text = validate_request(request, directory)
    root = validate_model(request.get('model_path'))
    # No Hub access, credentials, remote code, pickle, or cache fallback.
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    import torch
    from transformers import AutoTokenizer, LlamaForCausalLM
    cuda = torch.cuda.is_available()
    import psutil
    import shutil
    available=psutil.virtual_memory().available
    gpu_free=torch.cuda.mem_get_info(0)[0] if cuda else 0
    if available<13*1024**3 or (cuda and gpu_free<4*1024**3) or shutil.disk_usage(directory).free<25*1024**3:
        raise ValueError('memory_budget_unavailable')
    torch.manual_seed(0)
    if cuda:
        torch.cuda.set_device(0)
        torch.cuda.reset_peak_memory_stats(0)
    def synchronize():
        if cuda:
            torch.cuda.synchronize(0)
    phase('loading')
    synchronize()
    start = time.monotonic()
    tokenizer = AutoTokenizer.from_pretrained(str(root), local_files_only=True, trust_remote_code=False)
    encoded = tokenizer.apply_chat_template([{'role': 'user', 'content': text}],
        tokenize=True, add_generation_prompt=True, return_tensors='pt', return_dict=True)
    count = int(encoded['input_ids'].shape[-1])
    if not 0 < count <= 256:
        raise ValueError('input_token_limit')
    memory = {'cpu': '4GiB'}
    if cuda:
        memory[0] = '3GiB'
    write(directory/'placement.json',dict(status='loading',actual_device_map=None,placement_budget=dict(gpu_bytes=3*1024**3 if cuda else 0,cpu_bytes=4*1024**3),ram_available_before_bytes=available,gpu_free_before_bytes=gpu_free,memory_budget_is_os_hard_quota=False))
    model = LlamaForCausalLM.from_pretrained(str(root), local_files_only=True,
        trust_remote_code=False, use_safetensors=True, torch_dtype=torch.float16,
        low_cpu_mem_usage=True, device_map='auto', max_memory=memory,
        offload_folder=str(directory / 'offload'), offload_state_dict=True).eval()
    write(directory/'placement.json',dict(status='loaded',actual_device_map={str(k):str(v) for k,v in getattr(model,'hf_device_map',{}).items()},placement_budget=dict(gpu_bytes=3*1024**3 if cuda else 0,cpu_bytes=4*1024**3),ram_available_before_bytes=available,gpu_free_before_bytes=gpu_free,memory_budget_is_os_hard_quota=False))
    if count + 64 > model.config.max_position_embeddings:
        raise ValueError('input_token_limit')
    eos = model.generation_config.eos_token_id
    eos = [eos] if isinstance(eos, int) else eos
    if not isinstance(eos, list) or not eos or any(type(v) is not int for v in eos):
        raise ValueError('model_invalid')
    # Accelerate's hooks dispatch from the embedding execution device.
    encoded = {name: value.to(model.device) for name, value in encoded.items()}
    synchronize()
    loading = time.monotonic() - start
    phase('running')
    synchronize()
    start = time.monotonic()
    with torch.inference_mode():
        tokens = model.generate(**encoded, do_sample=False, num_beams=1,
            max_new_tokens=64, eos_token_id=eos, pad_token_id=tokenizer.pad_token_id or eos[0],
            use_cache=True, max_time=300.0)
    synchronize()
    elapsed = time.monotonic() - start
    generated = tokens[0, count:].tolist()
    reason = finish_reason(generated, eos)
    response = tokenizer.decode(generated, skip_special_tokens=True).strip()
    if not response:
        raise ValueError('output_invalid')
    phase('validating')
    value = dict(text=response, finish_reason=reason, input_tokens=count,
                 generated_tokens=len(generated), parameters=dict(PARAMETERS))
    mapping = getattr(model, 'hf_device_map', {})
    devices = sorted(set(str(v) for v in mapping.values()))
    gpu_placed = any(v.isdecimal() or v == 'cuda' or v.startswith('cuda:') for v in devices)
    metrics = dict(loading_seconds=round(loading, 3), inference_seconds=round(elapsed, 3),
        peak_gpu_allocated_bytes=torch.cuda.max_memory_allocated(0) if cuda else 0,
        cold_loading=True, dtype='float16', seed=0, batch_size=1,
        input_tokens=count, generated_tokens=len(generated), finish_reason=reason,
        device=torch.cuda.get_device_name(0) if cuda else 'cpu',
        cuda_available=cuda, cpu_fallback=not gpu_placed, placement_devices=devices,
        cpu_offload='cpu' in devices, disk_offload='disk' in devices,
        memory_placement_budget=dict(gpu_bytes=3 * 1024**3 if cuda else 0, cpu_bytes=4 * 1024**3),
        ram_available_before_bytes=available,gpu_free_before_bytes=gpu_free,memory_budget_is_os_hard_quota=False,
        packages={name: importlib.metadata.version(name) for name in
                  ('torch', 'transformers', 'accelerate', 'safetensors', 'tokenizers')})
    publish(directory / 'response.txt', response.encode('utf8'))
    publish(directory / 'response.json', json.dumps(value, ensure_ascii=False, indent=2).encode('utf8'))
    return metrics


def main(argv=None):
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 1:
        return 2
    path = Path(arguments[0])
    directory = path.parent
    request = {}
    result = dict(run_id=None, input_sha256=None, status='failed')
    try:
        request = json.loads(path.read_text('utf8'))
        if isinstance(request, dict):
            result.update(run_id=request.get('run_id'), input_sha256=request.get('input_sha256'))
        def phase(status):
            write(directory / 'progress.json', dict(run_id=result['run_id'],
                input_sha256=result['input_sha256'], status=status))
        result['metrics'] = generate(request, directory, phase)
        result['status'] = 'generated'
    except Exception as error:
        code = str(error)
        result['error'] = (code if code in ERRORS else 'inference_out_of_memory'
            if type(error).__name__ in {'OutOfMemoryError', 'CUDAOutOfMemoryError', 'MemoryError'}
            else 'inference_failed')
        # Do not place paths, source input, credentials, or model contents in logs.
        print(result['error'], file=sys.stderr)
    write(directory / 'result.json', result)
    return 0 if result['status'] == 'generated' else 1


if __name__ == '__main__':
    raise SystemExit(main())
