"""Bounded URL-deduplicated atomic downloads, independent of OCR."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib
import json
import os
import uuid
import time
import urllib.request
import urllib.error
import ssl
import math
from email.utils import parsedate_to_datetime
from threading import Lock
from urllib.parse import urlsplit
from PIL import Image
from mye_c_automation.image_http import image_headers

DEFAULT_DOWNLOAD_OPTIONS=dict(max_retries=3,retry_base_seconds=2,retry_max_seconds=30,min_interval_seconds=1)

def validate_download_options(value):
    if not isinstance(value,dict) or set(value)!=set(DEFAULT_DOWNLOAD_OPTIONS):raise ValueError('INVALID_DOWNLOAD_OPTIONS')
    if type(value['max_retries']) is not int or not 0<=value['max_retries']<=10:raise ValueError('INVALID_DOWNLOAD_RETRIES')
    for key in ('retry_base_seconds','retry_max_seconds','min_interval_seconds'):
        if type(value[key]) not in (int,float) or not math.isfinite(value[key]) or not 0<=value[key]<=60:raise ValueError('INVALID_DOWNLOAD_INTERVAL')
    if value['retry_max_seconds']<value['retry_base_seconds']:raise ValueError('INVALID_DOWNLOAD_BACKOFF')
    return dict(value)

def load_download_options(directory=None):
    from mye_c_automation.paths import config_root
    path=config_root(directory)/'download.local.json'
    return validate_download_options(json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else DEFAULT_DOWNLOAD_OPTIONS)

def _retry_after(exc):
    value=exc.headers.get('Retry-After') if isinstance(exc,urllib.error.HTTPError) and exc.headers else None
    if value is None:return None
    try:return max(0,int(value))
    except (ValueError,TypeError):
        try:return max(0,parsedate_to_datetime(value).timestamp()-time.time())
        except (ValueError,TypeError,OverflowError):return None

def _transient(exc):
    if isinstance(exc,urllib.error.HTTPError):return exc.code in {408,425,429,500,502,503,504}
    reason=exc.reason if isinstance(exc,urllib.error.URLError) else exc
    if isinstance(reason,ssl.SSLError):return False
    return isinstance(exc,(TimeoutError,ConnectionError,urllib.error.URLError))


def seed_image_cache(job_directory, cache_directory):
    """Explicitly seed successful, sealed image bytes; never change source Jobs."""
    job=Path(job_directory).resolve();cache=Path(cache_directory).resolve()
    manifest=json.loads((job/'full_audit_evidence_manifest.json').read_text(encoding='utf-8'))
    bound={row['path'].replace('\\','/'):row['sha256'] for row in manifest['files']}
    inventory_path=job/'full_inventory.json'
    if hashlib.sha256(inventory_path.read_bytes()).hexdigest()!=bound.get('full_inventory.json'):
        raise ValueError('SOURCE_INVENTORY_CHANGED')
    inventory=json.loads(inventory_path.read_text(encoding='utf-8'))
    entries={}
    for digest,content in inventory['contents'].items():
        source=Path(content['file']).resolve()
        if not source.is_relative_to(job):raise ValueError('SOURCE_IMAGE_OUTSIDE_JOB')
        data=source.read_bytes()
        if hashlib.sha256(data).hexdigest()!=digest or bound.get(source.relative_to(job).as_posix())!=digest:
            raise ValueError('SOURCE_IMAGE_CHANGED')
        for url in content['urls']:
            target=cache/(hashlib.sha256(url.encode()).hexdigest()+'.bin')
            if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()!=digest:
                raise ValueError('CACHE_IMAGE_CONFLICT')
            entries[url]=(target,data,digest)
    # Validate every source before creating or writing any destination.
    cache.mkdir(parents=True,exist_ok=True)
    for target,data,digest in entries.values():
        if not target.exists():
            with target.open('xb') as stream:stream.write(data)
        checksum=target.with_suffix('.sha256')
        if checksum.exists() and checksum.read_text(encoding='ascii').strip()!=digest:
            raise ValueError('CACHE_CHECKSUM_CONFLICT')
        if not checksum.exists():checksum.write_text(digest,encoding='ascii')
    return dict(status='CACHE_SEEDED',source_job=str(job),cache_directory=str(cache),verified_urls=len(entries),network_calls=0,model_calls=0,source_modified=False)

def download_unique(urls, directory, downloader=None, workers=1, force=False, ttl_seconds=86400, max_bytes=33554432, metrics=None, *, reuse_successful=False, min_interval_seconds=1.0, max_retries=0, retry_base_seconds=2, retry_max_seconds=30):
    validate_download_options(dict(max_retries=max_retries,retry_base_seconds=retry_base_seconds,retry_max_seconds=retry_max_seconds,min_interval_seconds=min_interval_seconds))
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    rate_lock=Lock();host_locks={};last_started={};ready={}
    def cooldown_file(host):return directory/('backoff-'+hashlib.sha256(host.encode()).hexdigest()+'.json')
    def persisted_deadline(host):
        path=cooldown_file(host)
        if not path.exists():return 0
        value=json.loads(path.read_text(encoding='utf-8'))['retry_not_before']
        if type(value) not in (int,float) or not math.isfinite(value):raise ValueError('INVALID_DOWNLOAD_COOLDOWN')
        return value
    def defer_host(url,delay):
        with rate_lock:
            host=urlsplit(url).netloc.lower();ready[host]=max(ready.get(host,0),time.monotonic()+delay)
            from mye_c_automation.job_manager import atomic_json
            atomic_json(cooldown_file(host),dict(retry_not_before=max(persisted_deadline(host),time.time()+delay)))
    def pace(url):
        host=urlsplit(url).netloc.lower()
        with rate_lock:lock=host_locks.setdefault(host,Lock())
        with lock:
            while True:
                now=time.monotonic()
                interval=min_interval_seconds if downloader is None else 0
                with rate_lock:cooldown=ready.get(host,0)
                delay=max(0,last_started.get(host,now-interval)+interval-now,cooldown-now,persisted_deadline(host)-time.time())
                if delay>60:return delay
                if delay:time.sleep(delay)
                else:
                    last_started[host]=time.monotonic()
                    return 0
    def fetch(url):
        started=time.perf_counter()
        path = directory / (hashlib.sha256(url.encode()).hexdigest() + '.bin')
        temp = path.with_suffix('.' + uuid.uuid4().hex + '.tmp')
        checksum=path.with_suffix('.sha256')
        cached = path.exists() and 0 < path.stat().st_size <= max_bytes and not force and (reuse_successful or time.time()-path.stat().st_mtime < ttl_seconds)
        history=[]
        try:
            if cached and checksum.exists():cached=hashlib.sha256(path.read_bytes()).hexdigest()==checksum.read_text(encoding='ascii').strip()
            if cached:return url,{'path':path,'cached':True,'attempts':0,'attempt_history':[],'elapsed_ms':round((time.perf_counter()-started)*1000,3)}
            for attempt in range(max_retries+1):
              delay=pace(url)
              if delay:
                return url,dict(error='SERVER_RETRY_AFTER_PENDING',attempts=len(history),attempt_history=history,retry_status='WAIT_REQUIRED',retry_not_before=time.time()+delay,elapsed_ms=round((time.perf_counter()-started)*1000,3))
              try:
                if downloader is None:
                    with urllib.request.urlopen(urllib.request.Request(url, headers=image_headers()), timeout=30) as response, temp.open('wb') as output:
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
                checksum_temp=temp.with_suffix('.sha.tmp')
                try:
                    checksum_temp.write_text(hashlib.sha256(path.read_bytes()).hexdigest(),encoding='ascii')
                    os.replace(checksum_temp,checksum)
                finally:checksum_temp.unlink(missing_ok=True)
                history.append(dict(attempt=attempt+1,status='SUCCESS'))
                return url, {'path': path, 'cached': False,'attempts':len(history),'attempt_history':history,'elapsed_ms':round((time.perf_counter()-started)*1000,3)}
              except Exception as exc:
                temp.unlink(missing_ok=True)
                event=dict(attempt=attempt+1,status='FAILED',error_type=type(exc).__name__)
                if isinstance(exc,urllib.error.HTTPError):event['http_status']=exc.code
                retry_after=_retry_after(exc)
                if retry_after is not None:event['retry_after_seconds']=retry_after
                history.append(event)
                retryable=_transient(exc)
                if retryable and max_retries:
                    delay=max(min(retry_max_seconds,retry_base_seconds*2**attempt),retry_after or 0)
                    event['backoff_seconds']=delay;defer_host(url,delay)
                    if delay>60:
                        return url,dict(error=str(exc),http_status=getattr(exc,'code',None),attempts=len(history),attempt_history=history,retry_status='WAIT_REQUIRED',retry_not_before=time.time()+delay,elapsed_ms=round((time.perf_counter()-started)*1000,3))
                if not retryable or attempt==max_retries:raise
        except Exception as exc:
            failure={'error': str(exc),'attempts':len(history),'attempt_history':history,'retry_status':'EXHAUSTED' if max_retries and _transient(exc) else 'NOT_RETRYABLE' if max_retries else 'DISABLED','elapsed_ms':round((time.perf_counter()-started)*1000,3)}
            if isinstance(exc,urllib.error.HTTPError):
                failure['http_status']=exc.code
                value=_retry_after(exc)
                if value is not None:failure['retry_after_seconds']=value
            return url,failure
        finally:
            temp.unlink(missing_ok=True)
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 8))) as pool:
        results=dict(pool.map(fetch, dict.fromkeys(urls)))
    if metrics is not None:
        metrics.update(unique_urls=len(results),cache_hits=sum(bool(r.get('cached')) for r in results.values()),
            network_fetches=sum(r.get('attempts',0)>0 for r in results.values()),
            network_attempts=sum(r.get('attempts',0) for r in results.values()),
            retry_attempts=sum(max(0,r.get('attempts',0)-1) for r in results.values()),
            refreshed=sum(bool(force or ttl_seconds==0) and not r.get('cached',False) for r in results.values()),
            failed=sum('error' in r for r in results.values()),
            bytes_downloaded=sum(r['path'].stat().st_size for r in results.values() if 'path' in r and not r['cached']))
    return results
