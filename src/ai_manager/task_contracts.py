"""Bounded input/output contracts, independent of model packages."""
import base64
import hashlib
import io
import json
import math
from pathlib import Path
import struct
import wave
import zlib

MAX_WAV_BYTES = 960_128


def sha(data): return hashlib.sha256(data).hexdigest()


def wav_input(data):
    if not isinstance(data, bytes) or not 44 < len(data) <= MAX_WAV_BYTES: raise ValueError('input_audio_invalid')
    try:
        if data[:4]!=b'RIFF' or data[8:12]!=b'WAVE' or struct.unpack('<I',data[4:8])[0]+8!=len(data): raise ValueError()
        with wave.open(io.BytesIO(data),'rb') as reader:
            count, rate = reader.getnframes(), reader.getframerate()
            if rate!=16000 or reader.getnchannels()!=1 or reader.getsampwidth()!=2 or reader.getcomptype()!='NONE' or not 0<count<=480000: raise ValueError()
            frames=reader.readframes(count)
            if len(frames)!=count*2: raise ValueError()
        if not any(frames): raise ValueError()
        return dict(bytes=len(data),sha256=sha(data),sample_rate=rate,channels=1,frames=count,duration_seconds=count/rate)
    except (wave.Error,EOFError,OSError,ValueError,struct.error): raise ValueError('input_audio_invalid') from None


def decode_input(payload,task_type='stt'):
    if task_type=='image':
        if not isinstance(payload,dict) or set(payload)!={'prompt'} or not isinstance(payload['prompt'],str) or len(payload['prompt'])>2000:raise ValueError('input_prompt_invalid')
        try:return decode_input({'text':payload['prompt']},'llm')
        except ValueError:raise ValueError('input_prompt_invalid') from None
    if task_type=='llm':
        if not isinstance(payload,dict) or set(payload)!={'text'} or not isinstance(payload['text'],str) or not payload['text'].strip():raise ValueError('input_text_invalid')
        try:data=payload['text'].encode('utf8')
        except UnicodeError:raise ValueError('input_text_invalid') from None
        if len(data)>8192 or any(ord(c)<32 and c not in '\n\r\t' for c in payload['text']):raise ValueError('input_text_invalid')
        return data,dict(bytes=len(data),sha256=sha(data))
    if task_type=='tracking':
        if not isinstance(payload,dict) or set(payload)!={'video_base64','points'} or not isinstance(payload['video_base64'],str) or len(payload['video_base64'])>6_666_672:raise ValueError('input_video_invalid')
        points=payload['points']
        if not isinstance(points,list) or not 1<=len(points)<=8:raise ValueError('input_points_invalid')
        for point in points:
            if not isinstance(point,dict) or set(point)!={'x','y'} or any(type(point[k]) not in (int,float) or not math.isfinite(point[k]) or not 0<=point[k]<=1 for k in ('x','y')):raise ValueError('input_points_invalid')
        try:data=base64.b64decode(payload['video_base64'],validate=True)
        except (ValueError,TypeError):raise ValueError('input_video_invalid') from None
        if not 12<=len(data)<=5_000_000 or data[4:8]!=b'ftyp':raise ValueError('input_video_invalid')
        return data,dict(bytes=len(data),sha256=sha(data),points=points)
    if task_type!='stt':raise ValueError('adapter_unsupported')
    if not isinstance(payload,dict) or set(payload)!={'audio_base64'} or not isinstance(payload['audio_base64'],str) or len(payload['audio_base64'])>1_281_000:
        raise ValueError('input_audio_invalid')
    try: data=base64.b64decode(payload['audio_base64'],validate=True)
    except (ValueError,TypeError): raise ValueError('input_audio_invalid') from None
    return data,wav_input(data)


OUTPUTS = {'transcript':dict(filename='transcript.json',mime='application/json',extension='.json'),
           'text':dict(filename='transcript.txt',mime='text/plain; charset=utf-8',extension='.txt'),
           'response':dict(filename='response.json',mime='application/json',extension='.json'),
           'response_text':dict(filename='response.txt',mime='text/plain; charset=utf-8',extension='.txt'),
           'tracks':dict(filename='tracks.json',mime='application/json',extension='.json'),
           'preview':dict(filename='preview.png',mime='image/png',extension='.png'),
           'image':dict(filename='image.png',mime='image/png',extension='.png'),
           'image_metadata':dict(filename='image.json',mime='application/json',extension='.json')}


def response(value):
    if not isinstance(value,dict) or set(value)!={'text','finish_reason','input_tokens','generated_tokens','parameters'}:raise ValueError('output_invalid')
    text=value['text']
    if not isinstance(text,str) or not text.strip() or len(text.encode('utf8'))>32768 or value['finish_reason'] not in ('eos','length'):raise ValueError('output_invalid')
    if type(value['input_tokens']) is not int or not 0<value['input_tokens']<=256 or type(value['generated_tokens']) is not int or not 0<value['generated_tokens']<=64:raise ValueError('output_invalid')
    if value['finish_reason']=='length' and value['generated_tokens']!=64:raise ValueError('output_invalid')
    if value['parameters']!=dict(max_new_tokens=64,max_input_tokens=256,seed=0,do_sample=False):raise ValueError('output_invalid')
    return text


def tracks(value):
    if not isinstance(value,dict) or value.get('width')!=256 or value.get('height')!=256 or value.get('query_frame')!=0 or value.get('coordinates')!='resized_pixel_xy':raise ValueError('output_invalid')
    count=value.get('frame_count');points=value.get('points');fps=value.get('fps')
    if type(count) is not int or not 2<=count<=32 or type(fps) not in (int,float) or not math.isfinite(fps) or not 0<fps<=120 or not isinstance(points,list) or not 1<=len(points)<=8:raise ValueError('output_invalid')
    for point in points:
        if not isinstance(point,dict) or set(point)!={'x','y'} or any(type(point[k]) not in (int,float) or not math.isfinite(point[k]) or not 0<=point[k]<=1 for k in ('x','y')):raise ValueError('output_invalid')
    trajectories=value.get('tracks');occlusions=value.get('occluded')
    if not isinstance(trajectories,list) or not isinstance(occlusions,list) or len(trajectories)!=len(points) or len(occlusions)!=len(points):raise ValueError('output_invalid')
    for trajectory,occluded in zip(trajectories,occlusions):
        if not isinstance(trajectory,list) or len(trajectory)!=count or not isinstance(occluded,list) or len(occluded)!=count or any(type(v) is not bool for v in occluded):raise ValueError('output_invalid')
        for point in trajectory:
            if not isinstance(point,list) or len(point)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>1_000_000 for v in point):raise ValueError('output_invalid')
    source=value.get('source')
    if not isinstance(source,dict) or type(source.get('width')) is not int or type(source.get('height')) is not int or not 1<=source['width']<=3840 or not 1<=source['height']<=2160 or source.get('frames')!=count:raise ValueError('output_invalid')
    times=source.get('timestamps_seconds')
    if not isinstance(times,list) or len(times)!=count or any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in times) or any(a>=b for a,b in zip(times,times[1:])):raise ValueError('output_invalid')
    if times[-1]-times[0]>20:raise ValueError('output_invalid')


def png(data):
    """Validate CRCs, supported PNG structure and bounded full decompression."""
    if data[:8]!=b'\x89PNG\r\n\x1a\n' or len(data)>5_000_000:raise ValueError('output_invalid')
    offset=8;header=None;compressed=bytearray();ended=False
    while offset<len(data):
        if offset+12>len(data):raise ValueError('output_invalid')
        size=struct.unpack('>I',data[offset:offset+4])[0];kind=data[offset+4:offset+8];start=offset+8;end=start+size
        if end+4>len(data) or zlib.crc32(data[offset+4:end])&0xffffffff!=struct.unpack('>I',data[end:end+4])[0]:raise ValueError('output_invalid')
        chunk=data[start:end]
        if header is None and kind!=b'IHDR':raise ValueError('output_invalid')
        if kind==b'IHDR':
            if header is not None or size!=13:raise ValueError('output_invalid')
            header=struct.unpack('>IIBBBBB',chunk)
            width,height,depth,color,compression,filtering,interlace=header
            if not 1<=width<=1024 or not 1<=height<=1024 or depth!=8 or color not in (2,6) or compression or filtering or interlace:raise ValueError('output_invalid')
        elif kind==b'IDAT':compressed.extend(chunk)
        elif kind==b'IEND':
            if size or end+4!=len(data):raise ValueError('output_invalid')
            ended=True
        elif kind[0]&32==0:raise ValueError('output_invalid')
        offset=end+4
    if not ended or not compressed:raise ValueError('output_invalid')
    row=header[0]*(3 if header[3]==2 else 4)+1;expected=row*header[1]
    try:
        decoder=zlib.decompressobj();pixels=decoder.decompress(bytes(compressed),expected+1)
        if len(pixels)!=expected or not decoder.eof or decoder.unused_data or any(pixels[i] not in range(5) for i in range(0,expected,row)):raise ValueError()
    except (zlib.error,ValueError):raise ValueError('output_invalid') from None
    return dict(width=header[0],height=header[1],mode='RGB' if header[3]==2 else 'RGBA')


def transcript(data):
    if not isinstance(data,dict) or set(data)!={'text','language','input_duration_seconds','timestamps'} or data['language']!='ko' or data['timestamps'] is not None:
        raise ValueError('output_invalid')
    text=data['text']
    if not isinstance(text,str) or not text.strip() or len(text)>12000 or any(ord(c)<32 and c not in '\n\t\r' for c in text): raise ValueError('output_invalid')
    duration=data['input_duration_seconds']
    if type(duration) not in (int,float) or not math.isfinite(duration) or not 0<duration<=30: raise ValueError('output_invalid')
    return text


def output(directory, output_id, home):
    from .inference import regular
    if output_id not in OUTPUTS: raise ValueError('output_not_found')
    meta=OUTPUTS[output_id]
    path=regular(Path(directory)/meta['filename'],Path(home))
    if not path.is_file() or not 0<path.stat().st_size<=5_000_000: raise ValueError('output_invalid')
    data=path.read_bytes()
    try:
        if output_id in {'text','transcript','response','response_text'}:
            stt=output_id in {'text','transcript'}
            value=json.loads(regular(Path(directory)/('transcript.json' if stt else 'response.json'),Path(home)).read_text('utf8'))
            text=transcript(value) if stt else response(value)
            if output_id in {'text','response_text'} and data!=text.encode('utf8'):raise ValueError()
            if output_id in {'transcript','response'} and json.loads(data)!=value:raise ValueError()
        elif output_id=='tracks':tracks(json.loads(data))
        elif output_id in {'image','image_metadata'}:
            from .image_safe import validate_png,validate_image_metadata
            image=validate_png(regular(Path(directory)/'image.png',Path(home)))
            metadata=validate_image_metadata(regular(Path(directory)/'image.json',Path(home)))
            if metadata.get('image')!=image:raise ValueError('output_invalid')
        else:
            from .image_safe import validate_png
            validate_png(path,width=768,height=280)
    except (ValueError,OSError,UnicodeError): raise ValueError('output_invalid') from None
    return data, dict(id=output_id,**meta,bytes=len(data),sha256=sha(data))
