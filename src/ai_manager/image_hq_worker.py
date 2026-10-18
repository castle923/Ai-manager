"""One explicitly selected official 2K image candidate; no automatic retries.

Separate from the Windows/local smoke contract. Parent owns external RAM/GPU
observation, wall timeout, cancellation, immutable model bytes and process cleanup.
No model downloads, security changes or movement of existing offloaded objects.
"""
import io
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ai_manager.image_diagnostics import ImageDiagnostics
from ai_manager.image_safe import read_prompt, regular_file, validate_png
from ai_manager.image_worker import (DIFFUSERS_REVISION, ERROR_CODES, GIB, MODEL_REVISION,
    check_model_index, check_runtime, publish_bytes, write)

PROFILE = 'qwen-image-2.1-official-hq-single-v1'
PARAMETERS = dict(seed=42, width=2048, height=2048, num_inference_steps=40, true_cfg_scale=1.0,
    num_images_per_prompt=1, negative_prompt=None, use_kv_cache=True)
PROMPT = ('A monumental stone observatory on a rugged coastal cliff at sunrise, waves breaking far below, '
    'intricate weathered stone carvings, copper instruments and clear glass lenses, wild grasses moving in '
    'the sea breeze, luminous clouds, rich natural textures, cinematic yet physically plausible lighting, '
    'balanced composition, extraordinary fine detail, no text, no logo, no watermark.')
MAX_PNG_BYTES = 32 * 1024 * 1024
MAX_WALL_SECONDS = 1500
MAX_RSS_BYTES = 64 * GIB


def validate_request(request, directory):
    if request.get('profile') != PROFILE or request.get('parameters') != PARAMETERS:
        raise ValueError('input_parameters_invalid')
    # Exact key/value types reject bool==1 and int==float aliases.
    if any(type(request['parameters'][key]) is not type(value) for key, value in PARAMETERS.items()):
        raise ValueError('input_parameters_invalid')
    if not isinstance(request.get('run_id'), str) or not re.fullmatch('[A-Za-z0-9_-]{1,128}', request['run_id']):
        raise ValueError('input_prompt_invalid')
    if not isinstance(request.get('input_metadata'), dict):
        raise ValueError('input_changed')
    prompt = read_prompt(directory / 'input.txt', request.get('input_sha256'), request['input_metadata'])
    if prompt != PROMPT:
        raise ValueError('input_prompt_invalid')
    for name in ('image.png', 'image.json', 'image-offload'):
        if (directory / name).exists() or (directory / name).is_symlink():
            raise ValueError('output_exists')
    return prompt


def resources(torch, psutil, directory, started, *, initial=False):
    """Fail-closed observations, not OS quotas or proof of future peak capacity."""
    if time.monotonic() - started > MAX_WALL_SECONDS:
        raise ValueError('generation_timeout')
    free, total = torch.cuda.mem_get_info(0)
    available = psutil.virtual_memory().available
    rss = psutil.Process().memory_info().rss
    if rss > MAX_RSS_BYTES or available < 8 * GIB or free < 4 * GIB:
        raise ValueError('resource_limit_reached')
    if initial and (total < 78 * GIB or free < 70 * GIB or available < 64 * GIB
                    or shutil.disk_usage(directory).free < GIB):
        raise ValueError('memory_budget_unavailable')
    return dict(gpu_free_bytes=int(free), gpu_total_bytes=int(total),
        ram_available_bytes=int(available), process_rss_bytes=int(rss))


def verify_unhooked(pipeline):
    if getattr(pipeline, 'hf_device_map', None):
        raise ValueError('runtime_version_mismatch')
    for name in ('transformer', 'text_encoder', 'vae'):
        model = getattr(pipeline, name)
        if getattr(model, 'hf_device_map', None) or any(getattr(module, '_hf_hook', None) is not None for module in model.modules()):
            raise ValueError('runtime_version_mismatch')


def verify_full_gpu(pipeline, torch):
    verify_unhooked(pipeline)
    for name in ('transformer', 'text_encoder', 'vae'):
        model = getattr(pipeline, name)
        count = 0
        for parameters, tensors in ((True, model.parameters()), (False, model.buffers())):
            for tensor in tensors:
                count += 1
                if tensor.device.type != 'cuda' or tensor.device.index not in (None, 0):
                    raise ValueError('runtime_version_mismatch')
                # Official modules may intentionally retain fp32 rotary/scaling
                # buffers. Require bf16 model parameters, preserving buffers'
                # official dtype while still requiring their CUDA placement.
                if parameters and tensor.is_floating_point() and tensor.dtype != torch.bfloat16:
                    raise ValueError('runtime_version_mismatch')
        if not count:
            raise ValueError('runtime_version_mismatch')


def load_pipeline(model_path, torch, diagnostic, guard):
    from transformers import Qwen3VLProcessor
    from diffusers import QwenImage21Pipeline
    diagnostic.mark('processor_load')
    processor = Qwen3VLProcessor.from_pretrained(str(model_path), subfolder='processor',
        local_files_only=True, trust_remote_code=False)
    guard()
    diagnostic.mark('pipeline_construct')
    # Official fixed model-card path: a NEW pipeline without device_map,
    # Accelerate hooks or CPU/disk offload, then .to('cuda'). The processor
    # override merely reuses this run's small preflight-loaded component.
    pipeline = QwenImage21Pipeline.from_pretrained(str(model_path), dtype=torch.bfloat16,
        local_files_only=True, use_safetensors=True, processor=processor)
    guard()
    diagnostic.mark('pipeline_configure')
    verify_unhooked(pipeline)
    pipeline.to('cuda')
    verify_full_gpu(pipeline, torch)
    pipeline.set_progress_bar_config(disable=True)
    guard()
    return pipeline


def validate_metadata(path, expected_input_sha256=None):
    path = regular_file(path)
    if not 0 < path.stat().st_size <= 32768:
        raise ValueError('output_invalid')
    try:
        value = json.loads(path.read_text('utf8'))
        if value['profile'] != PROFILE or value['parameters'] != PARAMETERS or value['pipeline_class'] != 'QwenImage21Pipeline':
            raise ValueError('output_invalid')
        if any(type(value['parameters'][key]) is not type(expected) for key, expected in PARAMETERS.items()):
            raise ValueError('output_invalid')
        if value['model_revision'] != MODEL_REVISION or value['diffusers_revision'] != DIFFUSERS_REVISION:
            raise ValueError('output_invalid')
        if not re.fullmatch('[a-f0-9]{64}', value['prompt_sha256']) or value['quality_assessed'] is not False:
            raise ValueError('output_invalid')
        if value['input_sha256'] != value['prompt_sha256'] or not re.fullmatch('[A-Za-z0-9_-]{1,128}', value['run_id']):
            raise ValueError('output_invalid')
        if expected_input_sha256 is not None and value['prompt_sha256'] != expected_input_sha256:
            raise ValueError('output_invalid')
        if value['conditions']['memory_strategy'] != 'new_pipeline_full_gpu_bfloat16' or value['conditions']['smoke_only'] is not False:
            raise ValueError('output_invalid')
        if (type(value['conditions']['pipeline_calls']) is not int or value['conditions']['pipeline_calls'] != 1
                or type(value['conditions']['automatic_retries']) is not int or value['conditions']['automatic_retries'] != 0
                or value['conditions']['hardware_recipe_e2e_verified'] is not False
                or value['conditions']['absolute_maximum_quality_claimed'] is not False):
            raise ValueError('output_invalid')
        if value['image'] != validate_png(path.parent / 'image.png', 2048, 2048, MAX_PNG_BYTES):
            raise ValueError('output_invalid')
        return value
    except (KeyError, TypeError, UnicodeError, json.JSONDecodeError):
        raise ValueError('output_invalid') from None


def run(request_path):
    request_path = regular_file(request_path)
    directory = request_path.parent
    request = json.loads(request_path.read_text('utf8'))
    result = dict(run_id=request.get('run_id'), input_sha256=request.get('input_sha256'), status='failed', profile=PROFILE)
    diagnostic = ImageDiagnostics(directory)
    started = time.monotonic()
    def phase(status):
        write(directory / 'progress.json', dict(run_id=result['run_id'], status=status, profile=PROFILE))
    try:
        prompt = validate_request(request, directory)
        check_model_index(request['model_path'])
        os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1',
            HF_ENABLE_PARALLEL_LOADING='false', HF_PARALLEL_LOADING_WORKERS='1')
        diagnostic.emit('profile', profile=PROFILE)
        diagnostic.mark('runtime_import')
        import torch
        import psutil
        if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
            raise ValueError('adapter_runtime_not_ready')
        diagnostic.mark('runtime_check')
        diagnostic.runtime()
        packages = check_runtime()
        diagnostic.mark('memory_preflight')
        before = resources(torch, psutil, directory, started, initial=True)
        guard = lambda: resources(torch, psutil, directory, started)
        torch.manual_seed(42)
        torch.cuda.reset_peak_memory_stats()
        phase('loading')
        load_started = time.monotonic()
        pipeline = load_pipeline(Path(request['model_path']), torch, diagnostic, guard)
        diagnostic.mark('loading_synchronize')
        torch.cuda.synchronize()
        guard()
        loading = time.monotonic() - load_started
        diagnostic.mark('prompt_recheck')
        if read_prompt(directory / 'input.txt', request['input_sha256'], request['input_metadata']) != prompt:
            raise ValueError('input_changed')
        def step_guard(_pipeline, _step, _timestep, values):
            guard()
            return values
        phase('running')
        diagnostic.mark('inference')
        inference_started = time.monotonic()
        with torch.inference_mode():
            # Exactly one call; no warmup, retries, extra seed or output batch.
            images = pipeline(prompt=prompt, negative_prompt=None, true_cfg_scale=1.0,
                width=2048, height=2048, output_resolution=2048, num_inference_steps=40,
                num_images_per_prompt=1, use_kv_cache=True, output_type='pil',
                generator=torch.Generator('cuda').manual_seed(42),
                callback_on_step_end=step_guard, callback_on_step_end_tensor_inputs=[]).images
        diagnostic.mark('inference_synchronize')
        torch.cuda.synchronize()
        guard()
        elapsed = time.monotonic() - inference_started
        diagnostic.mark('output_validation')
        if len(images) != 1 or images[0].size != (2048, 2048) or images[0].mode not in ('RGB', 'RGBA'):
            raise ValueError('output_invalid')
        from PIL import Image
        buffer = io.BytesIO()
        fresh = Image.frombytes(images[0].mode, images[0].size, images[0].tobytes())
        fresh.save(buffer, format='PNG', optimize=False, interlace=0)
        if not 0 < buffer.tell() <= MAX_PNG_BYTES:
            raise ValueError('output_invalid')
        diagnostic.mark('output_publish')
        publish_bytes(directory / 'image.png', buffer.getvalue())
        image = validate_png(directory / 'image.png', 2048, 2048, MAX_PNG_BYTES)
        metadata = dict(run_id=result['run_id'], profile=PROFILE, input_sha256=request['input_sha256'],
            prompt_sha256=request['input_sha256'], parameters=dict(PARAMETERS), image=image,
            pipeline_class='QwenImage21Pipeline', model_revision=MODEL_REVISION, diffusers_revision=DIFFUSERS_REVISION,
            quality_assessed=False, conditions=dict(dtype='bfloat16', cold_loading=True, offline=True,
                memory_strategy='new_pipeline_full_gpu_bfloat16', smoke_only=False,
                official_recommended_example=True, absolute_maximum_quality_claimed=False,
                resource_guard_is_os_quota=False, hardware_recipe_e2e_verified=False,
                pipeline_calls=1, automatic_retries=0, max_wall_seconds=MAX_WALL_SECONDS,
                max_process_rss_bytes=MAX_RSS_BYTES))
        publish_bytes(directory / 'image.json', json.dumps(metadata, ensure_ascii=False, indent=2).encode('utf8'))
        validate_metadata(directory / 'image.json', request['input_sha256'])
        result.update(status='generated', metrics=dict(loading_seconds=round(loading, 3), inference_seconds=round(elapsed, 3),
            peak_gpu_allocated_bytes=torch.cuda.max_memory_allocated(), peak_gpu_reserved_bytes=torch.cuda.max_memory_reserved(),
            packages=packages, before=before, after=guard()))
    except Exception as error:
        code = str(error)
        permitted = ERROR_CODES | {'generation_timeout', 'resource_limit_reached'}
        result['error'] = code if code in permitted else 'inference_out_of_memory' if type(error).__name__ in {'OutOfMemoryError', 'CUDAOutOfMemoryError', 'MemoryError'} else 'inference_failed'
        diagnostic.failure(error, result['error'])
        print(result['error'], file=sys.stderr)
    finally:
        diagnostic.close()
    write(directory / 'result.json', result)
    return 0 if result['status'] == 'generated' else 1


def entrypoint():
    if len(sys.argv) != 2:
        return 2
    try:
        return run(Path(sys.argv[1]))
    except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError):
        return 1


if __name__ == '__main__':
    raise SystemExit(entrypoint())
