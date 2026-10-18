"""One offline Qwen-Image-2.1 smoke, in a parent-owned cancellable process.

The catalog gate MUST remain blocked until a fresh 8GB/32GB execution passes.
Accelerate's placement budgets below are not OS memory quotas. This module
neither downloads weights nor changes security settings. The parent owns timeout,
cancel, subprocess-tree termination and model-manifest byte verification.
"""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time
import uuid

if not __package__:
    # -I omits the script directory. Add only this installed package's parent.
    sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from ai_manager.image_safe import read_prompt, regular_file, validate_parameters, validate_png
from ai_manager.image_diagnostics import ImageDiagnostics

MODEL_REVISION = 'd26bb61231c349cf6b7896fa83353113880e1ba3'
DIFFUSERS_REVISION = 'b800f828f3951c4d206e154411bcbfa693cd322e'
MODEL_INDEX_SHA256 = 'cf1ecd104ea090855d60d8cec0895c1e9d6ee41b2f87e231b678beecd1cf7809'
PIPELINE_SOURCE_SHA256 = 'e75e4ce38d38e194edaac818bba99b2115b4bb2bfdbd15ce03a2813b0fe8856c'
GIB = 1024 ** 3
MEMORY_REQUIREMENTS = dict(gpu_free_min_bytes=7 * GIB, gpu_total_min_bytes=7 * GIB,
    ram_available_min_bytes=18 * GIB, disk_free_min_bytes=40 * GIB)
# Aggregate persistent placement: <=4 GiB GPU +12 GiB CPU plus VAE.
# This reserves capacity for CUDA context, active offloaded blocks, activations,
# the largest source shard and Python. Only fresh execution can validate peaks.
PLACEMENT = {'text_encoder': {0: 2 * GIB, 'cpu': 6 * GIB},
             'transformer': {0: 2 * GIB, 'cpu': 6 * GIB}}
ERROR_CODES = {'input_changed', 'input_prompt_invalid', 'input_parameters_invalid',
               'input_path_invalid', 'model_configuration_invalid', 'adapter_runtime_not_ready',
               'runtime_version_mismatch', 'memory_budget_unavailable', 'output_invalid',
               'output_exists', 'inference_out_of_memory'}


def write(path, value):
    temporary = path.with_name(uuid.uuid4().hex + '.tmp')
    with temporary.open('x', encoding='utf8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
    os.replace(temporary, path)


def publish_bytes(path, data):
    temporary = path.with_name(uuid.uuid4().hex + '.partial')
    with temporary.open('xb') as stream:
        stream.write(data)
    try:
        os.link(temporary, path)  # exclusive publication, never replace an output
    finally:
        temporary.unlink()


def check_model_index(model_path):
    path = regular_file(Path(model_path) / 'model_index.json')
    if path.stat().st_size > 8192 or hashlib.sha256(path.read_bytes()).hexdigest() != MODEL_INDEX_SHA256:
        raise ValueError('model_configuration_invalid')


def check_runtime():
    # Verify the *installed* pipeline against the fixed official source; a
    # matching package version alone does not identify a mutable git build.
    import diffusers.pipelines.qwenimage21.pipeline_qwenimage21 as source
    if hashlib.sha256(Path(source.__file__).read_bytes()).hexdigest() != PIPELINE_SOURCE_SHA256:
        raise ValueError('runtime_version_mismatch')
    expected = {'transformers': '5.17.0', 'accelerate': '1.12.0', 'torch': '2.9.1+cu128',
                'torchvision': '0.24.1+cu128',
                'safetensors': '0.8.0', 'Pillow': '11.3.0', 'psutil': '7.2.2'}
    try:
        packages = {name: importlib.metadata.version(name) for name in expected}
    except importlib.metadata.PackageNotFoundError as error:
        raise ValueError('runtime_version_mismatch') from error
    if packages != expected:
        raise ValueError('runtime_version_mismatch')
    packages['diffusers_git_revision'] = DIFFUSERS_REVISION
    packages['pipeline_source_sha256'] = PIPELINE_SOURCE_SHA256
    return packages


def memory_preflight(torch, psutil, directory):
    free, total = torch.cuda.mem_get_info(0)
    # These checks reserve headroom but are not a hard resource controller.
    if (free < MEMORY_REQUIREMENTS['gpu_free_min_bytes'] or total < MEMORY_REQUIREMENTS['gpu_total_min_bytes']
            or psutil.virtual_memory().available < MEMORY_REQUIREMENTS['ram_available_min_bytes']
            or shutil.disk_usage(directory).free < MEMORY_REQUIREMENTS['disk_free_min_bytes']):
        raise ValueError('memory_budget_unavailable')
    return dict(gpu_free_before_bytes=free, gpu_total_bytes=total,
                ram_available_before_bytes=psutil.virtual_memory().available)


def load_pipeline(model_path, directory, torch, diagnostic=None):
    previous_tempdir = tempfile.tempdir
    own_diagnostic = diagnostic is None
    diagnostic = diagnostic or ImageDiagnostics(directory)
    try:
        return _load_pipeline(model_path, directory, torch, diagnostic)
    finally:
        tempfile.tempdir = previous_tempdir
        if own_diagnostic:
            diagnostic.close()


def _load_pipeline(model_path, directory, torch, diagnostic=None):
    """Load official components independently, with RAM/GPU/disk dispatch.

    Diffusers ModelMixin pinned source supports low_cpu_mem_usage and
    offload_state_dict. Transformers 5.17 always uses empty/meta initialization
    and safetensors streaming; its deprecated low_cpu_mem_usage and
    offload_state_dict kwargs are discarded, so we deliberately omit those.
    No pipeline .to('cuda') or component-wide model_cpu_offload is used.
    """
    diagnostic.mark('component_import')
    from accelerate import cpu_offload
    from diffusers import (AutoencoderKLQwenImage21, FlowMatchEulerDiscreteScheduler,
                           QwenImage21Pipeline, QwenImage21Transformer2DModel)
    from transformers import Qwen3VLForConditionalGeneration, Qwen3VLProcessor
    # The fixed processor includes Qwen3VLVideoProcessor. Transformers 5.17's
    # AutoVideoProcessor requires torchvision even for this text-to-image run.
    # Validate that small local component before any multi-GB model load.
    diagnostic.mark('processor_load')
    processor = Qwen3VLProcessor.from_pretrained(
        str(model_path), subfolder='processor', local_files_only=True, trust_remote_code=False)
    diagnostic.mark('offload_setup')
    offload = directory / 'image-offload'
    offload.mkdir(exist_ok=False)
    scratch = offload / 'temporary'
    scratch.mkdir()
    # Diffusers' public offload_state_dict implementation creates a temporary
    # backing directory. Keep that library scratch in this new run as well.
    tempfile.tempdir = str(scratch)
    common = dict(local_files_only=True, use_safetensors=True, dtype=torch.bfloat16)
    # Largest fixed transformer shard is 9,968,332,504 bytes. Load it BEFORE
    # allocating the text encoder's CPU backing to reduce simultaneous peak.
    diagnostic.mark('transformer_load')
    transformer = QwenImage21Transformer2DModel.from_pretrained(
        str(model_path), subfolder='transformer', device_map='auto',
        max_memory=dict(PLACEMENT['transformer']), offload_folder=str(offload / 'transformer'),
        low_cpu_mem_usage=True, offload_state_dict=True, **common).eval()
    diagnostic.placement('transformer', transformer)
    diagnostic.mark('text_encoder_load')
    text_encoder = Qwen3VLForConditionalGeneration.from_pretrained(
        str(model_path), subfolder='text_encoder', trust_remote_code=False,
        device_map='auto', max_memory=dict(PLACEMENT['text_encoder']),
        offload_folder=str(offload / 'text_encoder'), offload_buffers=True, **common).eval()
    # VAE is much smaller than either main component. Its CPU backing stays in
    # RAM while Accelerate brings leaf modules to the execution GPU on demand.
    diagnostic.placement('text_encoder', text_encoder)
    diagnostic.mark('vae_load')
    vae = AutoencoderKLQwenImage21.from_pretrained(
        str(model_path), subfolder='vae', low_cpu_mem_usage=True, **common).eval()
    diagnostic.mark('vae_offload')
    cpu_offload(vae, execution_device=torch.device('cuda:0'), offload_buffers=True)
    diagnostic.mark('scheduler_load')
    scheduler = FlowMatchEulerDiscreteScheduler.from_pretrained(
        str(model_path), subfolder='scheduler', local_files_only=True)
    # The fixed checkpoint has no custom sample_sigmas; respect that exact
    # index, not a pipeline discovered from arbitrary repository code.
    index = json.loads((Path(model_path) / 'model_index.json').read_text('utf8'))
    diagnostic.mark('pipeline_construct')
    pipe = QwenImage21Pipeline(scheduler=scheduler, vae=vae, text_encoder=text_encoder,
                              processor=processor, transformer=transformer,
                              sample_sigmas=index.get('sample_sigmas'))
    diagnostic.mark('pipeline_configure')
    pipe.set_progress_bar_config(disable=True)
    return pipe


def run(request_path):
    request_path = regular_file(request_path)
    directory = request_path.parent
    request = json.loads(request_path.read_text('utf8'))
    result = dict(run_id=request.get('run_id'), input_sha256=request.get('input_sha256'), status='failed')
    diagnostic = ImageDiagnostics(directory)
    def phase(status):
        write(directory / 'progress.json', dict(run_id=result['run_id'], status=status))
    try:
        if not isinstance(result['run_id'], str) or not re.fullmatch('[A-Za-z0-9_-]{1,128}', result['run_id']):
            raise ValueError('input_prompt_invalid')
        parameters = validate_parameters(request.get('parameters'))
        metadata = request.get('input_metadata')
        if not isinstance(metadata, dict):
            raise ValueError('input_changed')
        prompt = read_prompt(directory / 'input.txt', request['input_sha256'], metadata)
        for name in ('image.png', 'image.json', 'image-offload'):
            if (directory / name).exists() or (directory / name).is_symlink():
                raise ValueError('output_exists')
        check_model_index(request['model_path'])
        # Offline flags supplement local_files_only; they do not claim a network
        # firewall. Set only for this disposable worker process.
        os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1',
                          HF_ENABLE_PARALLEL_LOADING='false', HF_PARALLEL_LOADING_WORKERS='1')
        diagnostic.mark('runtime_import')
        import torch
        import psutil
        if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
            raise ValueError('adapter_runtime_not_ready')
        diagnostic.mark('runtime_check')
        diagnostic.runtime()
        packages = check_runtime()
        diagnostic.mark('memory_preflight')
        before = memory_preflight(torch, psutil, directory)
        torch.manual_seed(0)
        torch.cuda.reset_peak_memory_stats()
        phase('loading')
        diagnostic.mark('loading')
        started = time.monotonic()
        pipeline = load_pipeline(Path(request['model_path']), directory, torch, diagnostic)
        diagnostic.mark('loading_synchronize')
        torch.cuda.synchronize()
        loading = time.monotonic() - started
        # Recheck immediately before using the immutable in-memory prompt.
        diagnostic.mark('prompt_recheck')
        if read_prompt(directory / 'input.txt', request['input_sha256'], metadata) != prompt:
            raise ValueError('input_changed')
        phase('running')
        diagnostic.mark('inference')
        started = time.monotonic()
        with torch.inference_mode():
            images = pipeline(prompt=prompt, negative_prompt='', true_cfg_scale=parameters['guidance_scale'],
                              width=512, height=512, num_inference_steps=4,
                              num_images_per_prompt=1, use_kv_cache=False,
                              generator=torch.Generator('cuda:0').manual_seed(0), output_type='pil').images
        diagnostic.mark('inference_synchronize')
        torch.cuda.synchronize()
        elapsed = time.monotonic() - started
        diagnostic.mark('output_validation')
        if len(images) != 1 or images[0].size != (512, 512) or images[0].mode not in ('RGB', 'RGBA'):
            raise ValueError('output_invalid')
        phase('validating')
        import io
        buffer = io.BytesIO()
        # Rebuild pixels to drop arbitrary metadata and keep only RGB(A)8 PNG.
        from PIL import Image
        fresh = Image.frombytes(images[0].mode, images[0].size, images[0].tobytes())
        fresh.save(buffer, format='PNG', optimize=False, interlace=0)
        diagnostic.mark('output_publish')
        publish_bytes(directory / 'image.png', buffer.getvalue())
        image_info = validate_png(directory / 'image.png')
        conditions = dict(dtype='bfloat16', seed=0, cold_loading=True, offline=True,
                          guidance_parameter='true_cfg_scale', negative_prompt='', use_kv_cache=False,
                          memory_strategy='component_auto_device_map_cpu_disk',
                          placement_budgets_bytes={name: {str(k): v for k, v in budget.items()} for name, budget in PLACEMENT.items()},
                          memory_budget_is_os_hard_quota=False, hardware_recipe_e2e_verified=False,
                          purpose='research_evaluation_personal_experiment', license='Qwen Research License',
                          smoke_only=True, official_example_steps=40, official_example_width=2048)
        value = dict(run_id=result['run_id'], input_sha256=request['input_sha256'],
                     prompt_sha256=request['input_sha256'], parameters=parameters, image=image_info,
                     pipeline_class='QwenImage21Pipeline', model_revision=MODEL_REVISION,
                     diffusers_revision=DIFFUSERS_REVISION, quality_assessed=False, conditions=conditions)
        publish_bytes(directory / 'image.json', json.dumps(value, ensure_ascii=False, indent=2).encode('utf8'))
        diagnostic.mark('metrics')
        process_memory = psutil.Process().memory_info()
        result.update(status='generated', metrics=dict(loading_seconds=round(loading, 3),
                      inference_seconds=round(elapsed, 3), peak_gpu_allocated_bytes=torch.cuda.max_memory_allocated(),
                      peak_gpu_reserved_bytes=torch.cuda.max_memory_reserved(),
                      process_rss_end_bytes=process_memory.rss,
                      process_peak_rss_bytes=getattr(process_memory, 'peak_wset', None),
                      cold_loading=True, dtype='bfloat16', seed=0,
                      device=torch.cuda.get_device_name(0), packages=packages, **before))
    except Exception as error:
        code = str(error)
        result['error'] = code if code in ERROR_CODES else 'inference_out_of_memory' if type(error).__name__ in {'OutOfMemoryError', 'CUDAOutOfMemoryError', 'MemoryError'} else 'inference_failed'
        # Only a stable code reaches logs; exception text can contain private
        # prompt/model paths. Parent records this process's bounded stderr.
        diagnostic.failure(error, result['error'])
        print(result['error'], file=sys.stderr)
    finally:
        diagnostic.close()
    write(directory / 'result.json', result)
    return 0 if result['status'] == 'generated' else 1


def main():
    if len(sys.argv) != 2:
        return 2
    return run(Path(sys.argv[1]))


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
