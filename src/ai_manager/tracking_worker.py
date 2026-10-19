"""Local, isolated BootsTAPIR v2 worker. No model-provided code is imported."""
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import time
import uuid


def write(path, value, replace=True):
    temporary = path.with_name(uuid.uuid4().hex + '.partial')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), 'utf8')
    if replace:
        os.replace(temporary, path)
    else:
        os.link(temporary, path)
        temporary.unlink()


def preview(path, frames, tracks, occluded):
    from PIL import Image, ImageDraw
    indices = [0, len(frames) // 2, len(frames) - 1]
    canvas = Image.new('RGB', (768, 280), '#111827')
    draw = ImageDraw.Draw(canvas)
    colors = ['#ff3355', '#33ff88', '#33bbff', '#ffcc33', '#ff66ff', '#ffffff', '#ff9933', '#99ffff']
    for column, frame in enumerate(indices):
        canvas.paste(Image.fromarray(frames[frame], 'RGB'), (column * 256, 24))
        draw.text((column * 256 + 8, 6), 'Frame ' + str(frame), fill='white')
        for point, trajectory in enumerate(tracks):
            x, y = trajectory[frame]
            if 0 <= x <= 255 and 0 <= y <= 255:
                x += column * 256
                y += 24
                box = (x-4, y-4, x+4, y+4)
                draw.ellipse(box, outline=colors[point], width=2, fill=None if occluded[point][frame] else colors[point])
    temporary = path.with_name(uuid.uuid4().hex + '.partial')
    canvas.save(temporary, format='PNG')
    os.link(temporary, path)
    temporary.unlink()


def main():
    request_path = Path(sys.argv[1]).resolve(strict=True)
    directory = request_path.parent
    request = json.loads(request_path.read_text('utf8'))
    result = dict(run_id=request['run_id'], input_sha256=request['input_sha256'], status='failed')
    def phase(status):
        write(directory / 'progress.json', dict(run_id=request['run_id'], status=status))
    try:
        # -I intentionally excludes script paths. Add only this installed, trusted package root.
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        import torch
        import numpy as np
        from ai_manager.tapir_safe import parameters, decode_video, load_checkpoint, validate_outputs
        from ai_manager.tapir_vendor.tapir_model import TAPIR
        points, limit = parameters(request['parameters'])
        frames, source = decode_video(directory / 'input.mp4', request['input_sha256'], limit)
        if not torch.cuda.is_available():
            raise ValueError('adapter_runtime_not_ready')
        torch.set_num_threads(2)
        torch.manual_seed(0)
        torch.cuda.reset_peak_memory_stats()
        phase('loading')
        started = time.monotonic()
        model = TAPIR(pyramid_level=1, extra_convs=True, use_casual_conv=False)
        expected = '8493c7a69e02c85b9382fbb3c7b8b539b36bc08ede744b9e99feb739a0129f4b'
        if request.get('model_sha256') != expected:
            raise ValueError('tracking_checkpoint_hash_mismatch')
        checkpoint_hash = load_checkpoint(torch, model, Path(request['model_path']) / 'bootstapir_checkpoint_v2.pt', expected)
        model = model.to('cuda').eval()
        torch.cuda.synchronize()
        loading = time.monotonic() - started
        phase('running')
        started = time.monotonic()
        video = torch.from_numpy(frames.copy()).float().to('cuda')[None] / 127.5 - 1
        queries = torch.tensor([[[0., p['y'] * 255., p['x'] * 255.] for p in points]], dtype=torch.float32, device='cuda')
        with torch.inference_mode():
            output = model(video, queries, is_training=False, query_chunk_size=8)
        torch.cuda.synchronize()
        inference = time.monotonic() - started
        phase('validating')
        tracks, occluded = validate_outputs(torch, output, len(points), len(frames))
        data = dict(points=points, frame_count=len(frames), width=256, height=256, fps=source['fps'],
            tracks=tracks, occluded=occluded, source=source, query_frame=0, coordinates='resized_pixel_xy',
            run_id=request['run_id'], input_sha256=request['input_sha256'], model_sha256=checkpoint_hash,
            model='BootsTAPIR v2', vendor_revision='730cda1c730877cfedbe01bf87fb1cadb78a565d')
        write(directory / 'tracks.json', data, replace=False)
        preview(directory / 'preview.png', frames, tracks, occluded)
        result.update(status='generated', metrics=dict(loading_seconds=round(loading, 3), inference_seconds=round(inference, 3),
            peak_gpu_allocated_bytes=torch.cuda.max_memory_allocated(), cold_loading=True, dtype='float32', seed=0,
            device=torch.cuda.get_device_name(0), frame_count=len(frames), point_count=len(points),
            packages={name: importlib.metadata.version(name) for name in ('torch', 'numpy', 'Pillow', 'av', 'dm-tree', 'einshape')}))
    except Exception as error:
        code = str(error)
        result['error'] = code if code in {'tracking_parameters_invalid', 'tracking_points_invalid', 'input_changed',
            'input_video_invalid', 'input_video_resource_limit', 'tracking_checkpoint_invalid',
            'tracking_checkpoint_hash_mismatch', 'tracking_output_invalid', 'adapter_runtime_not_ready'} else (
                'inference_out_of_memory' if type(error).__name__ in {'OutOfMemoryError', 'CUDAOutOfMemoryError'} else 'inference_failed')
        import traceback
        traceback.print_exc()
    write(directory / 'result.json', result)
    return 0 if result['status'] == 'generated' else 1


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
