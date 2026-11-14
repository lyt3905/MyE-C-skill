"""Bounded URL-deduplicated atomic downloads, independent of OCR."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib
import os
import uuid
import time
import urllib.request
from PIL import Image

def download_unique(urls, directory, downloader=None, workers=6, force=False, ttl_seconds=86400, max_bytes=33554432, metrics=None):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    def fetch(url):
        started=time.perf_counter()
        path = directory / (hashlib.sha256(url.encode()).hexdigest() + '.bin')
        temp = path.with_suffix('.' + uuid.uuid4().hex + '.tmp')
        cached = path.exists() and path.stat().st_size > 0 and not force and time.time()-path.stat().st_mtime < ttl_seconds
        try:
            if not cached:
                if downloader is None:
                    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0','Accept':'image/jpeg,image/png,image/webp,image/*;q=0.8','Referer':'https://www.aliexpress.com/'}), timeout=30) as response, temp.open('wb') as output:
                        mime=response.headers.get('Content-Type','').split(';')[0]
                        if not mime.startswith('image/'): raise ValueError('invalid image content type')
                        total=0
                        while True:
                            chunk=response.read(65536)
                            if not chunk: break
                            total+=len(chunk)
                            if total > max_bytes: raise ValueError('download exceeds byte limit')
                            output.write(chunk)
                    with Image.open(temp) as image:
                        actual=Image.MIME.get(image.format)
                        image.verify()
                    if actual != mime: raise ValueError('image MIME mismatch')
                else:
                    downloader(url, str(temp))
                if not temp.exists() or not temp.stat().st_size:
                    raise ValueError('empty download')
                if temp.stat().st_size > max_bytes: raise ValueError('download exceeds byte limit')
                os.replace(temp, path)
            return url, {'path': path, 'cached': cached,'elapsed_ms':round((time.perf_counter()-started)*1000,3)}
        except Exception as exc:
            return url, {'error': str(exc),'elapsed_ms':round((time.perf_counter()-started)*1000,3)}
        finally:
            temp.unlink(missing_ok=True)
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 8))) as pool:
        results=dict(pool.map(fetch, dict.fromkeys(urls)))
    if metrics is not None:
        metrics.update(unique_urls=len(results),cache_hits=sum(bool(r.get('cached')) for r in results.values()),
            network_fetches=sum(not r.get('cached',False) for r in results.values()),
            refreshed=sum(bool(force or ttl_seconds==0) and not r.get('cached',False) for r in results.values()),
            failed=sum('error' in r for r in results.values()),
            bytes_downloaded=sum(r['path'].stat().st_size for r in results.values() if 'path' in r and not r['cached']))
    return results
