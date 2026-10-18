"""Bounded prompt and PNG validation, with no inference dependencies."""
import hashlib
import json
from pathlib import Path
import re
import stat
import struct
import zlib

PARAMETERS = dict(seed=0, width=512, height=512, num_inference_steps=4, guidance_scale=4.0)
MAX_PNG_BYTES = 2 * 1024 * 1024


def regular_file(path):
    path = Path(path)
    # Resolve neither symlinks nor Windows reparse points on the input boundary.
    for part in (path, *path.parents):
        info = part.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('input_path_invalid')
    if not path.is_file():
        raise ValueError('input_path_invalid')
    return path


def read_prompt(path, expected_sha256, metadata=None):
    path = regular_file(path)
    if not isinstance(expected_sha256, str) or not re.fullmatch('[a-f0-9]{64}', expected_sha256):
        raise ValueError('input_changed')
    if not 0 < path.stat().st_size <= 8192:
        raise ValueError('input_prompt_invalid')
    with path.open('rb') as stream:
        data = stream.read(8193)
    if len(data) > 8192 or hashlib.sha256(data).hexdigest() != expected_sha256:
        raise ValueError('input_changed')
    if metadata is not None and (metadata.get('sha256') != expected_sha256 or type(metadata.get('bytes')) is not int or metadata['bytes'] != len(data)):
        raise ValueError('input_changed')
    try:
        text = data.decode('utf8', errors='strict')
    except UnicodeDecodeError:
        raise ValueError('input_prompt_invalid') from None
    if not text.strip() or len(text) > 2000 or any(ord(c) < 32 and c not in '\n\r\t' for c in text):
        raise ValueError('input_prompt_invalid')
    return text


def validate_parameters(value):
    if not isinstance(value, dict) or value != PARAMETERS:
        raise ValueError('input_parameters_invalid')
    if any(type(value.get(name)) is not int for name in ('seed', 'width', 'height', 'num_inference_steps')):
        raise ValueError('input_parameters_invalid')
    if type(value.get('guidance_scale')) not in (int, float):
        raise ValueError('input_parameters_invalid')
    return dict(PARAMETERS)


def validate_png(path, width=512, height=512, max_bytes=MAX_PNG_BYTES):
    path = regular_file(path)
    if not 0 < path.stat().st_size <= max_bytes:
        raise ValueError('output_invalid')
    data = path.read_bytes()
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('output_invalid')
    offset, chunks, compressed, color, ended, idat_ended = 8, [], bytearray(), None, False, False
    while offset < len(data):
        if offset + 12 > len(data):
            raise ValueError('output_invalid')
        size = struct.unpack('>I', data[offset:offset + 4])[0]
        kind = data[offset + 4:offset + 8]
        end = offset + 12 + size
        if end > len(data):
            raise ValueError('output_invalid')
        payload = data[offset + 8:offset + 8 + size]
        crc = struct.unpack('>I', data[end - 4:end])[0]
        if zlib.crc32(kind + payload) & 0xffffffff != crc:
            raise ValueError('output_invalid')
        if not chunks and kind != b'IHDR':
            raise ValueError('output_invalid')
        if kind == b'IHDR':
            if chunks or size != 13:
                raise ValueError('output_invalid')
            w, h, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', payload)
            if (w, h) != (width, height) or depth != 8 or color not in (2, 6) or (compression, filtering, interlace) != (0, 0, 0):
                raise ValueError('output_invalid')
        elif kind == b'IDAT':
            if idat_ended:
                raise ValueError('output_invalid')
            compressed.extend(payload)
        elif kind == b'IEND':
            if size or not compressed or end != len(data):
                raise ValueError('output_invalid')
            ended = True
        else:
            # Fresh worker output is deliberately metadata-free. Reject unknown
            # chunks, animation, embedded prompts and external provenance.
            raise ValueError('output_invalid')
        if compressed and kind != b'IDAT':
            idat_ended = True
        chunks.append(kind)
        offset = end
    if not ended:
        raise ValueError('output_invalid')
    channels = 3 if color == 2 else 4
    stride = width * channels + 1
    expected = height * stride
    try:
        decoder = zlib.decompressobj()
        pixels = decoder.decompress(bytes(compressed), expected + 1)
        if len(pixels) != expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail or any(pixels[y * stride] > 4 for y in range(height)):
            raise ValueError('output_invalid')
    except zlib.error:
        raise ValueError('output_invalid') from None
    return dict(width=width, height=height, mode='RGB' if color == 2 else 'RGBA', bit_depth=8, interlaced=False, bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def validate_image_metadata(path, expected_prompt_sha256=None):
    path = regular_file(path)
    if not 0 < path.stat().st_size <= 32768:
        raise ValueError('output_invalid')
    try:
        value = json.loads(path.read_text('utf8'))
        validate_parameters(value['parameters'])
        if not re.fullmatch('[a-f0-9]{64}', value['prompt_sha256']):
            raise ValueError('output_invalid')
        if expected_prompt_sha256 is not None and value['prompt_sha256'] != expected_prompt_sha256:
            raise ValueError('output_invalid')
        if value['pipeline_class'] != 'QwenImage21Pipeline' or value['quality_assessed'] is not False or not isinstance(value['conditions'], dict):
            raise ValueError('output_invalid')
        return value
    except (KeyError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
        raise ValueError('output_invalid') from None
