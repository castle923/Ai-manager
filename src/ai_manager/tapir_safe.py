"""Bounded, local TAPIR input/output and restricted checkpoint validation."""
import hashlib
import math
from pathlib import Path
import time

MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 32 * 1920 * 1080
CHECKPOINT_BYTES = 218886140


def parameters(value):
    if not isinstance(value, dict) or set(value) - {'points', 'max_frames', 'resize'}:
        raise ValueError('tracking_parameters_invalid')
    points = value.get('points')
    if not isinstance(points, list) or not 1 <= len(points) <= 8:
        raise ValueError('tracking_points_invalid')
    for point in points:
        if not isinstance(point, dict) or set(point) != {'x', 'y'}:
            raise ValueError('tracking_points_invalid')
        if any(type(point[k]) not in (int, float) or not math.isfinite(point[k]) or not 0 <= point[k] <= 1 for k in ('x', 'y')):
            raise ValueError('tracking_points_invalid')
    limit = value.get('max_frames', 32)
    resize = value.get('resize', 256)
    if type(limit) is not int or not 1 <= limit <= 32 or type(resize) is not int or resize != 256:
        raise ValueError('tracking_parameters_invalid')
    return points, limit


def decode_video(path, expected_sha256, limit=32):
    import av
    import numpy as np
    from PIL import Image
    path = Path(path)
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= MAX_BYTES:
        raise ValueError('input_video_invalid')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError('input_changed')
    started = time.monotonic()
    frames, times, pixels = [], [], 0
    with av.open(str(path), mode='r', options={'protocol_whitelist': 'file', 'enable_drefs': '0', 'use_absolute_path': '0'}) as container:
        videos = list(container.streams.video)
        if len(videos) != 1 or container.format.name not in ('mov,mp4,m4a,3gp,3g2,mj2', 'mov,mp4,m4a,3gp,3g2,mj2,psp'):
            raise ValueError('input_video_invalid')
        stream = videos[0]
        stream.thread_type = 'NONE'
        stream.codec_context.thread_count = 1
        width, height = stream.codec_context.width, stream.codec_context.height
        if not 1 <= width <= 1920 or not 1 <= height <= 1080:
            raise ValueError('input_video_resource_limit')
        fps = float(stream.average_rate or 0)
        if not math.isfinite(fps) or not 0 < fps <= 120:
            raise ValueError('input_video_invalid')
        if stream.frames and stream.frames > 32:
            raise ValueError('input_video_resource_limit')
        for frame in container.decode(stream):
            if time.monotonic() - started > 20 or len(frames) >= limit:
                raise ValueError('input_video_resource_limit')
            if frame.width != width or frame.height != height:
                raise ValueError('input_video_invalid')
            pixels += width * height
            if pixels > MAX_PIXELS or frame.pts is None or frame.time_base is None:
                raise ValueError('input_video_resource_limit')
            timestamp = float(frame.pts * frame.time_base)
            if not math.isfinite(timestamp) or timestamp < 0 or timestamp > 30 or times and timestamp <= times[-1]:
                raise ValueError('input_video_invalid')
            times.append(timestamp)
            rgb = frame.to_ndarray(format='rgb24')
            frames.append(np.asarray(Image.fromarray(rgb).resize((256, 256), Image.Resampling.BILINEAR)))
    if not frames:
        raise ValueError('input_video_invalid')
    return np.stack(frames), dict(width=width, height=height, frames=len(frames), fps=fps, timestamps_seconds=times,
        resize=dict(method='Pillow bilinear', width=256, height=256, aspect='stretch',
                    normalized_query_to_resized_xy='x*255,y*255',
                    normalized_query_to_source_xy='(x*255+0.5)*source_width/256-0.5,(y*255+0.5)*source_height/256-0.5',
                    resized_track_to_source_xy='(x+0.5)*source_width/256-0.5,(y+0.5)*source_height/256-0.5'))


def load_checkpoint(torch, model, path, expected_sha256):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size != CHECKPOINT_BYTES:
        raise ValueError('tracking_checkpoint_invalid')
    digest = hashlib.sha256()
    with path.open('rb') as reader:
        for chunk in iter(lambda: reader.read(1024 * 1024), b''):
            digest.update(chunk)
    if not isinstance(expected_sha256, str) or len(expected_sha256) != 64 or digest.hexdigest() != expected_sha256:
        raise ValueError('tracking_checkpoint_hash_mismatch')
    # Never retry with unsafe pickle or extend safe globals.
    state = torch.load(str(path), map_location='cpu', weights_only=True)
    target = model.state_dict()
    if type(state) is not dict and type(state).__name__ != 'OrderedDict':
        raise ValueError('tracking_checkpoint_invalid')
    if set(state) != set(target):
        raise ValueError('tracking_checkpoint_invalid')
    total = 0
    for key, value in state.items():
        if type(key) is not str or type(value) is not torch.Tensor or value.layout != torch.strided or value.device.type != 'cpu':
            raise ValueError('tracking_checkpoint_invalid')
        if value.shape != target[key].shape or value.dtype != target[key].dtype:
            raise ValueError('tracking_checkpoint_invalid')
        total += value.numel() * value.element_size()
        if total > 256 * 1024 * 1024 or not torch.isfinite(value).all().item():
            raise ValueError('tracking_checkpoint_invalid')
    model.load_state_dict(state, strict=True)
    return digest.hexdigest()


def validate_outputs(torch, output, points, frames):
    for key, shape in (('tracks', (1, points, frames, 2)), ('occlusion', (1, points, frames)), ('expected_dist', (1, points, frames))):
        value = output.get(key)
        if not isinstance(value, torch.Tensor) or tuple(value.shape) != shape or not torch.isfinite(value).all().item():
            raise ValueError('tracking_output_invalid')
    tracks = output['tracks'][0].detach().float().cpu()
    if (tracks.abs() > 4096).any().item():
        raise ValueError('tracking_output_invalid')
    visible = (1 - output['occlusion'].sigmoid()) * (1 - output['expected_dist'].sigmoid()) > 0.5
    return tracks.tolist(), (~visible[0]).detach().cpu().tolist()
