"""Download only the selected official PyTorch wheel, with range/hash validation."""
import concurrent.futures
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import shutil
import time
from urllib.parse import urljoin, urlsplit, unquote
import uuid

import requests

INDEX = 'https://download.pytorch.org/whl/cu128/torch/'
FILENAME = 'torch-2.9.1+cu128-cp310-cp310-win_amd64.whl'


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.links.extend(v for k, v in attrs if k == 'href')


def download():
    page = requests.get(INDEX, timeout=30)
    page.raise_for_status()
    parser = Links()
    parser.feed(page.text)
    links = [urljoin(INDEX, link) for link in parser.links if unquote(urlsplit(link).path).endswith('/' + FILENAME)]
    if len(links) != 1:
        raise RuntimeError('official_wheel_not_unique')
    parsed = urlsplit(links[0])
    if parsed.scheme != 'https' or parsed.hostname not in ('download.pytorch.org', 'download-r2.pytorch.org') or not parsed.fragment.startswith('sha256='):
        raise RuntimeError('untrusted_wheel_source')
    expected = parsed.fragment.split('=', 1)[1]
    url = links[0].split('#', 1)[0]
    head = requests.head(url, timeout=30)
    head.raise_for_status()
    size = int(head.headers['Content-Length'])
    etag = head.headers.get('ETag')
    if not etag:
        raise RuntimeError('wheel_etag_missing')
    root = Path(os.environ['LOCALAPPDATA']) / 'AiManager' / 'm1-20261016' / 'runtime' / 'wheels' / uuid.uuid4().hex
    root.mkdir(parents=True, exist_ok=False)
    if shutil.disk_usage(root).free < size + 512 * 1024 * 1024:
        raise RuntimeError('insufficient_disk')
    target = root / FILENAME
    partial = target.with_suffix('.whl.part')
    with partial.open('xb') as handle:
        handle.truncate(size)
    started = time.monotonic()
    block_size = 8 * 1024 * 1024

    def fetch(start):
        end = min(size - 1, start + block_size - 1)
        for attempt in range(5):
            with requests.get(url, headers={'Range': f'bytes={start}-{end}', 'If-Range': etag, 'Accept-Encoding': 'identity'}, stream=True, timeout=(10, 45)) as response:
                if response.status_code in (429, 500, 502, 503, 504) and attempt < 4:
                    time.sleep(min(16, 2 ** attempt))
                    continue
                if response.status_code != 206 or response.headers.get('Content-Range') != f'bytes {start}-{end}/{size}' or response.headers.get('ETag') != etag:
                    raise RuntimeError('wheel_range_or_version_changed')
                count = 0
                with partial.open('r+b') as handle:
                    handle.seek(start)
                    for chunk in response.iter_content(256 * 1024):
                        count += len(chunk)
                        if count > end - start + 1:
                            raise RuntimeError('wheel_size_mismatch')
                        handle.write(chunk)
                if count != end - start + 1:
                    raise RuntimeError('wheel_size_mismatch')
                return count
        raise RuntimeError('wheel_retry_exhausted')

    starts = iter(range(0, size, block_size))
    total = 0
    last_report = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        pending = [pool.submit(fetch, next(starts)) for _ in range(min(8, (size + block_size - 1) // block_size))]
        while pending:
            total += pending.pop(0).result()
            next_start = next(starts, None)
            if next_start is not None:
                pending.append(pool.submit(fetch, next_start))
            elapsed = time.monotonic() - started
            if elapsed - last_report >= 10:
                print(json.dumps({'wheel_bytes': total, 'total_bytes': size, 'seconds': round(elapsed, 2), 'bytes_per_second': round(total / elapsed)}), flush=True)
                last_report = elapsed
    digest = hashlib.sha256()
    with partial.open('rb') as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b''):
            digest.update(chunk)
    if partial.stat().st_size != size or digest.hexdigest() != expected:
        raise RuntimeError('wheel_hash_mismatch')
    os.link(partial, target)
    partial.unlink()
    provenance = {'source': url, 'index': INDEX, 'sha256': expected, 'size': size, 'etag': etag, 'elapsed_seconds': round(time.monotonic() - started, 3)}
    (root / 'provenance.json').write_text(json.dumps(provenance, indent=2), encoding='utf8')
    (root.parent.parent / 'verified_wheel.json').write_text(json.dumps({'path': str(target), **provenance}, indent=2), encoding='utf8')
    print(json.dumps({'wheel_verified': True, 'sha256': expected, 'size': size}), flush=True)


if __name__ == '__main__':
    download()
