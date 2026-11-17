"""Runtime requests remain Mock HTTP; no external connections or old Job edits."""
import copy
from contextlib import closing
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
from unittest.mock import patch
from PIL import Image
from mye_c_automation.download_manager import download_unique
from mye_c_automation.model_config import validate_config, fingerprint

PROFILE = dict(schema='model-gateway/v1', base_url='http://127.0.0.1:8788/v1',
               models=['deepseek-v4.1-flash'], max_output_tokens=8192, retries=0,
               timeout=150, reasoning_effort='low', image_concurrency=2)


class DownloadTuningTests(unittest.TestCase):
    def test_seed_verified_job_cache_preserves_all_source_files(self):
        from mye_c_automation.download_manager import seed_image_cache
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);job=root/'job';job.mkdir()
            image=job/'audit_images/image.bin';image.parent.mkdir();image.write_bytes(b'original')
            digest=hashlib.sha256(image.read_bytes()).hexdigest()
            inventory=job/'full_inventory.json'
            inventory.write_text(json.dumps({'contents':{digest:{'file':str(image),'urls':['https://x/a','https://x/b']}}}))
            manifest={'files':[{'path':str(p.relative_to(job)).replace('/','\\'),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in (image,inventory)]}
            (job/'full_audit_evidence_manifest.json').write_text(json.dumps(manifest))
            before={p.relative_to(job).as_posix():p.read_bytes() for p in job.rglob('*') if p.is_file()}
            result=seed_image_cache(job,root/'cache')
            self.assertEqual(result['verified_urls'],2)
            self.assertEqual(before,{p.relative_to(job).as_posix():p.read_bytes() for p in job.rglob('*') if p.is_file()})
            def forbidden(*args):raise AssertionError('successful source fetched again')
            reused=download_unique(['https://x/a','https://x/b'],root/'cache',forbidden,reuse_successful=True,ttl_seconds=0)
            self.assertTrue(all(r['cached'] for r in reused.values()))
            image.write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError,'SOURCE'):
                seed_image_cache(job,root/'other-cache')
            self.assertFalse((root/'other-cache').exists())

    def test_explicit_reuse_fetches_only_failed_urls_even_after_ttl(self):
        with tempfile.TemporaryDirectory() as root:
            calls = []
            def first(url, path):
                calls.append(url)
                if url == 'bad':
                    raise OSError('temporary unavailable')
                Path(path).write_bytes(b'original-success')
            download_unique(['ok', 'ok', 'bad'], root, first)
            calls.clear()
            def second(url, path):
                calls.append(url)
                Path(path).write_bytes(b'new-success')
            result = download_unique(['ok', 'bad'], root, second, ttl_seconds=0, reuse_successful=True)
            self.assertEqual(calls, ['bad'])
            self.assertTrue(result['ok']['cached'])
            self.assertEqual(result['ok']['path'].read_bytes(), b'original-success')

    def test_corrupt_success_cache_is_not_reused(self):
        with tempfile.TemporaryDirectory() as root:
            def download(url, path):
                Path(path).write_bytes(b'good-source')
            initial = download_unique(['x'], root, download)
            initial['x']['path'].write_bytes(b'corrupt-cache')
            calls = []
            def repaired(url, path):
                calls.append(url)
                download(url, path)
            result = download_unique(['x'], root, repaired, reuse_successful=True)
            self.assertEqual(calls, ['x'])
            self.assertEqual(result['x']['path'].read_bytes(), b'good-source')

    def test_same_host_network_requests_are_serial_and_spaced(self):
        data = io.BytesIO()
        Image.new('RGB', (8, 8), 'red').save(data, format='PNG')
        clock = [0.0]
        starts = []
        class Reply(io.BytesIO):
            headers = {'Content-Type': 'image/png'}
        def send(request, **kwargs):
            starts.append(clock[0])
            return Reply(data.getvalue())
        with tempfile.TemporaryDirectory() as root, patch('mye_c_automation.download_manager.urllib.request.urlopen', side_effect=send), patch('mye_c_automation.download_manager.time.monotonic', side_effect=lambda: clock[0]), patch('mye_c_automation.download_manager.time.sleep', side_effect=lambda delay: clock.__setitem__(0, clock[0] + delay)):
            result = download_unique(['https://x/1', 'https://x/2', 'https://x/3'], root)
            self.assertEqual(starts, [0.0, 1.0, 2.0])
            self.assertTrue(all('path' in row for row in result.values()))

    def test_429_retains_retry_after_and_never_retries_automatically(self):
        error = urllib.error.HTTPError('https://x/1', 429, 'rate limited', {'Retry-After': '7'}, None)
        with tempfile.TemporaryDirectory() as root, patch('mye_c_automation.download_manager.urllib.request.urlopen', side_effect=error) as send:
            row = download_unique(['https://x/1', 'https://x/1'], root)['https://x/1']
            self.assertEqual(send.call_count, 1)
            self.assertEqual(row['http_status'], 429)
            self.assertEqual(row['retry_after_seconds'], 7)
            self.assertFalse(list(Path(root).glob('*.tmp')))

    def test_formal_downloads_reuse_shared_cache_but_snapshot_job_bytes(self):
        from mye_c_automation.full_product_audit import download_only
        data = io.BytesIO()
        Image.new('RGB', (8, 8), 'red').save(data, format='PNG')
        class Reader:
            def current_shop(self): return 7
            def product(self, pid): return dict(id=pid, images=dict(main=['https://x/image']))
        class Reply(io.BytesIO):
            headers = {'Content-Type': 'image/png'}
        with tempfile.TemporaryDirectory() as root, patch('mye_c_automation.download_manager.urllib.request.urlopen', side_effect=lambda *a, **k: Reply(data.getvalue())) as send:
            a = download_only(1, 7, output_dir=Path(root)/'JOB_first', site=Reader())
            b = download_only(1, 7, output_dir=Path(root)/'JOB_second', site=Reader())
            self.assertEqual(send.call_count, 1)
            first, second = Path(a['images'][0]['file']), Path(b['images'][0]['file'])
            self.assertTrue(first.is_relative_to(Path(root)/'JOB_first'))
            self.assertTrue(second.is_relative_to(Path(root)/'JOB_second'))
            self.assertNotEqual(first, second)
            second.write_bytes(b'later-mutation')
            self.assertEqual(first.read_bytes(), data.getvalue())


class ImageAuditTuningTests(unittest.TestCase):
    def test_controlled_budget_stays_serial_even_with_two_image_profile(self):
        from concurrent.futures import ThreadPoolExecutor
        from mye_c_automation.ai_judge import JudgeClient
        from mye_c_automation.budget_manager import BudgetManager
        from model_budget_fixtures import authorize_http_fake
        from test_v2_vision import observation
        with tempfile.TemporaryDirectory() as root:
            budget=BudgetManager({'ai_requests':10})
            try:
                # Configure strict policy before client construction.
                seed=JudgeClient(budget,Path(root)/'seed',config=PROFILE)
                authorize_http_fake(seed)
                client=JudgeClient(budget,Path(root)/'cache',config=PROFILE)
                lock=threading.Lock();active=peak=0
                def send(request,timeout):
                    nonlocal active,peak
                    item=json.loads(json.loads(request.data)['messages'][0]['content'][0]['text'].rsplit('\n',1)[-1])['item']
                    with lock:active+=1;peak=max(peak,active)
                    time.sleep(.02)
                    with lock:active-=1
                    return io.BytesIO(json.dumps({'choices':[{'message':{'content':json.dumps(observation(item))}}],'usage':dict(prompt_tokens=2,completion_tokens=3,total_tokens=5)}).encode())
                def classify(n):
                    return client.classify('image_action_decision',dict(id='A'+str(n),task_type='image_action_decision',image_type='MAIN',sha256=str(n)*64,evidence_ids=['A'+str(n)],dimensions=[800,800]),{'pid':1})
                with patch.dict('os.environ',{'VLM_API_KEY':'fake'}),patch('mye_c_automation.ai_judge.client._open_model_request',side_effect=send),ThreadPoolExecutor(max_workers=2) as pool:
                    results=list(pool.map(classify,(1,2)))
                self.assertEqual(peak,1,results)
                self.assertEqual(client.metrics['requests'],2,results)
                self.assertTrue(all(r['status']=='VALIDATED' for r in results))
            finally:budget.close()

    def test_default_configuration_uses_low_effort_and_two_images(self):
        from mye_c_automation.configuration import initialize_config
        with tempfile.TemporaryDirectory() as root:
            initialize_config(root)
            profile=json.loads((Path(root)/'model.local.json').read_text())
            self.assertEqual(profile['reasoning_effort'],'low')
            self.assertEqual(profile['image_concurrency'],2)
            self.assertEqual(profile['retries'],0)

    def test_two_image_profile_is_frozen_and_bad_concurrency_rejected(self):
        self.assertEqual(validate_config(PROFILE), PROFILE)
        self.assertNotEqual(fingerprint(PROFILE), fingerprint(dict(PROFILE, image_concurrency=1)))
        for value in (0, 11, True, '2', None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_config(dict(PROFILE, image_concurrency=value))

    def test_formal_v2_mock_http_overlaps_two_and_preserves_per_image_ledger(self):
        from mye_c_automation.full_product_audit import run_full_audit, download_only
        from test_v2_vision import observation
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            assets = {}
            for n, color in enumerate(('red', 'blue', 'green', 'yellow')):
                data = io.BytesIO()
                Image.new('RGB', (800, 800), color).save(data, format='PNG')
                assets['https://fake/'+str(n)] = data.getvalue()
            product = dict(id=1, images=dict(main=list(assets)), skus=[], descriptionJson=None)
            class Reader:
                def current_shop(self): return 7
                def account_fingerprint(self): return 'a'*64
                def product(self, pid): return copy.deepcopy(product)
            lock, gate = threading.Lock(), threading.Event()
            active = peak = 0
            sent = []
            def send(request, timeout):
                nonlocal active, peak
                body = json.loads(request.data)
                item = json.loads(body['messages'][0]['content'][0]['text'].rsplit('\n', 1)[-1])['item']
                with lock:
                    active += 1
                    peak = max(peak, active)
                    sent.append(body)
                    if active == 2: gate.set()
                gate.wait(2)
                try:
                    n = item['sha256'] == hashlib.sha256(assets['https://fake/2']).hexdigest()
                    from test_v2_vision import reply_for_prompt
                    value=reply_for_prompt(observation(item),body['messages'][0]['content'][0]['text'])
                    reply = {'choices': [{'finish_reason': 'length' if n else 'stop', 'message': {'content': '' if n else json.dumps(value), 'reasoning_content': 'PRIVATE_THINKING'}}]}
                    if item['sha256'] != hashlib.sha256(assets['https://fake/1']).hexdigest():
                        reply['usage'] = dict(prompt_tokens=2, completion_tokens=3, total_tokens=5)
                    return io.BytesIO(json.dumps(reply).encode())
                finally:
                    with lock: active -= 1
            def auditor(pid, shop, output_dir, site):
                return download_only(pid, shop, output_dir=output_dir, site=site, downloader=lambda url, path: Path(path).write_bytes(assets[url]))
            with patch.dict('os.environ', {'VLM_API_KEY': 'fake'}), patch('mye_c_automation.ai_judge.client._open_model_request', side_effect=send):
                report = run_full_audit(root/'jobs', 1, 7, Reader(), model_config=PROFILE, auditor=auditor)
            directory = root/'jobs'/report['job_id']
            self.assertEqual(peak, 2)
            self.assertEqual(len(sent), 4)
            self.assertTrue(all(b['reasoning_effort']=='low' and b['max_tokens']==8192 and len([x for x in b['messages'][0]['content'] if x['type']=='image_url'])==1 for b in sent))
            metrics = json.loads((directory/'full_ai_metrics.json').read_text())
            self.assertEqual((metrics['requests'], metrics['retries']), (4, 0))
            self.assertIsNone(metrics['total_tokens'])
            self.assertTrue(all(c['raw_response']['choices'][0]['message']['reasoning_content']=='PRIVATE_THINKING' for c in metrics['calls']))
            with closing(sqlite3.connect(directory/'budget.sqlite')) as db:
                self.assertEqual(db.execute('SELECT count(*) FROM model_calls').fetchone()[0], 4)
                self.assertEqual(db.execute("SELECT count(*) FROM model_calls WHERE state='UNKNOWN'").fetchone()[0], 1)
                self.assertTrue(all('PRIVATE_THINKING' in r[0] for r in db.execute('SELECT metadata FROM model_calls')))
            decisions = json.loads((directory/'full_ai_judgements.json').read_text())
            self.assertEqual(list(decisions), list(json.loads((directory/'full_inventory.json').read_text())['contents']))
            self.assertEqual(sum(r['decision']=='REVIEW' for r in decisions.values()), 1)
            self.assertEqual(report['audit_status'], 'INCOMPLETE')

    def test_cli_results_shows_final_json_without_reasoning_and_keeps_files(self):
        from mye_c_automation.job_manager import JobManager
        with tempfile.TemporaryDirectory() as root:
            manager = JobManager(Path(root)/'jobs')
            job = manager.create(1, 7, {}, mode='audit', image_workflow='v2')
            directory = manager.directory(job['job_id'])
            payload = {'a': {'decision':'DELETE', 'observation': {'decision':'DELETE','reason':'clean'}, 'results':[{'decision':'KEEP','reason':'clean'}], 'raw_response':{'reasoning_content':'PRIVATE_THINKING'}, 'policy_adjustments':[{'raw_decision':'KEEP','decision':'DELETE'}]}, 'b': {'decision':'REVIEW','observation':None,'results':[None],'reason_codes':['MODEL_OUTPUT_INCOMPLETE']}}
            path = directory/'full_ai_judgements.json'
            path.write_text(json.dumps(payload))
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            proc = subprocess.run([sys.executable, '-B', '-m', 'mye_c_automation', 'results', job['job_id'], '--root', str(manager.root)], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            result = json.loads(proc.stdout)
            self.assertNotIn('PRIVATE_THINKING', proc.stdout)
            self.assertEqual(result['items'][0]['final_json'], {'decision':'KEEP','reason':'clean'})
            self.assertEqual(result['items'][0]['decision'],'DELETE')
            self.assertEqual(result['items'][0]['policy_adjustments'],[{'raw_decision':'KEEP','decision':'DELETE'}])
            self.assertIsNone(result['items'][1]['final_json'])
            self.assertEqual(result['items'][1]['decision'], 'REVIEW')
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)
