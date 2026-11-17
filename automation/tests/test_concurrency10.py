"""User-selected ten-image concurrency through the formal V2 HTTP boundary."""
from contextlib import closing
import copy
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from PIL import Image
from mye_c_automation.model_config import validate_config

PROFILE=dict(schema='model-gateway/v1',base_url='http://127.0.0.1:8788/v1',models=['deepseek-v4.1-flash'],
             max_output_tokens=8192,retries=0,timeout=150,reasoning_effort='low',image_concurrency=10)


class TenImageConcurrencyTests(unittest.TestCase):
    def test_one_through_ten_are_valid_and_higher_values_rejected(self):
        from mye_c_automation.resources import validate_resource_json
        for value in range(1,11):
            with self.subTest(value=value):
                profile=validate_config(dict(PROFILE,image_concurrency=value))
                validate_resource_json(profile,'model-gateway.v1.schema.json')
                self.assertEqual(profile['image_concurrency'],value)
        for value in (0,11,32,True,'10',None):
            with self.subTest(value=value),self.assertRaises(ValueError):
                validate_config(dict(PROFILE,image_concurrency=value))

    def test_twelve_images_peak_at_ten_with_independent_results_and_ledger(self):
        from mye_c_automation.full_product_audit import run_full_audit,download_only
        from test_v2_vision import observation,reply_for_prompt
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);assets={}
            for n in range(12):
                stream=io.BytesIO();Image.new('RGB',(800,800),(n*17,60,100)).save(stream,format='PNG')
                assets['https://fake/'+str(n)]=stream.getvalue()
            product=dict(id=1,images={'main':list(assets)},skus=[],descriptionJson=None)
            class Reader:
                def current_shop(self):return 7
                def account_fingerprint(self):return 'a'*64
                def product(self,pid):return copy.deepcopy(product)
            lock=threading.Lock();gate=threading.Event();active=peak=0;sent=[]
            def send(request,timeout):
                nonlocal active,peak
                body=json.loads(request.data)
                item=json.loads(body['messages'][0]['content'][0]['text'].rsplit('\n',1)[-1])['item']
                with lock:
                    active+=1;peak=max(peak,active);sent.append(body)
                    if active==10:gate.set()
                gate.wait(2)
                try:
                    time.sleep(.01)
                    value=reply_for_prompt(observation(item),body['messages'][0]['content'][0]['text'])
                    return io.BytesIO(json.dumps({'choices':[{'finish_reason':'stop','message':{'content':json.dumps(value),
                        'reasoning_content':'ARCHIVED_THINKING'}}],'usage':{'prompt_tokens':2,'completion_tokens':3,'total_tokens':5}}).encode())
                finally:
                    with lock:active-=1
            def auditor(pid,shop,output_dir,site):
                return download_only(pid,shop,output_dir=output_dir,site=site,
                    downloader=lambda url,path:Path(path).write_bytes(assets[url]))
            with patch.dict('os.environ',{'VLM_API_KEY':'fake'}),patch('mye_c_automation.ai_judge.client._open_model_request',side_effect=send):
                result=run_full_audit(root/'jobs',1,7,Reader(),model_config=PROFILE,auditor=auditor)
            directory=root/'jobs'/result['job_id']
            self.assertEqual(peak,10)
            self.assertEqual(len(sent),12)
            self.assertTrue(all(b['reasoning_effort']=='low' and b['max_tokens']==8192 and
                sum(c['type']=='image_url' for c in b['messages'][0]['content'])==1 for b in sent))
            job=json.loads((directory/'job.json').read_text());self.assertEqual(job['model_config'],PROFILE)
            judgements=json.loads((directory/'full_ai_judgements.json').read_text())
            inventory=json.loads((directory/'full_inventory.json').read_text())
            self.assertEqual(list(judgements),list(inventory['contents']))
            self.assertTrue(all(v['decision']=='KEEP' for v in judgements.values()))
            metrics=json.loads((directory/'full_ai_metrics.json').read_text())
            self.assertEqual((metrics['requests'],metrics['retries'],metrics['total_tokens']),(12,0,60))
            self.assertEqual(len({r['item_id'] for r in metrics['calls']}),12)
            with closing(sqlite3.connect(directory/'budget.sqlite')) as db:
                self.assertEqual(db.execute('SELECT count(*),sum(actual) FROM model_calls').fetchone(),(12,60))
                self.assertEqual(db.execute("SELECT count(*) FROM model_calls WHERE state='SETTLED'").fetchone()[0],12)
            self.assertEqual(result['audit_status'],'COMPLETE')
            self.assertEqual((result['upload_calls'],result['site_save_calls']),(0,0))
