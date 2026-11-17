import io,json,tempfile,unittest,urllib.error
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from mye_c_automation.download_manager import download_unique

def png():
    data=io.BytesIO();Image.new('RGB',(8,8),'red').save(data,format='PNG');return data.getvalue()

class Reply(io.BytesIO):headers={'Content-Type':'image/png'}

class RetryTests(unittest.TestCase):
    def run_fake(self,send,urls=None,**options):
        clock=[1000.];starts=[]
        def call(*args,**kwargs):starts.append(clock[0]);return send(len(starts))
        with tempfile.TemporaryDirectory() as root,patch('mye_c_automation.download_manager.urllib.request.urlopen',side_effect=call),patch('mye_c_automation.download_manager.time.monotonic',side_effect=lambda:clock[0]),patch('mye_c_automation.download_manager.time.time',side_effect=lambda:clock[0]),patch('mye_c_automation.download_manager.time.sleep',side_effect=lambda d:clock.__setitem__(0,clock[0]+d)):
            metrics={};result=download_unique(urls or ['https://x/1'],root,max_retries=3,retry_base_seconds=2,retry_max_seconds=30,metrics=metrics,**options)
            self.assertFalse(list(Path(root).glob('*.tmp')))
            return result,starts,metrics

    def test_429_then_success_records_attempts_and_respects_retry_after(self):
        def send(n):
            if n==1:raise urllib.error.HTTPError('https://x/1',429,'slow',{'Retry-After':'7'},None)
            return Reply(png())
        result,starts,metrics=self.run_fake(send)
        row=result['https://x/1'];self.assertNotIn('error',row)
        self.assertEqual(starts,[1000.,1007.]);self.assertEqual(row['attempts'],2)
        self.assertEqual(row['attempt_history'][0]['http_status'],429)
        self.assertEqual(metrics['network_attempts'],2);self.assertEqual(metrics['retry_attempts'],1)

    def test_exhaustion_backoff_and_attempt_cap(self):
        def send(n):raise urllib.error.HTTPError('https://x/1',503,'temporary',{},None)
        result,starts,metrics=self.run_fake(send)
        self.assertEqual(starts,[1000.,1002.,1006.,1014.]);self.assertEqual(result['https://x/1']['attempts'],4)
        self.assertEqual(metrics['failed'],1);self.assertEqual(result['https://x/1']['retry_status'],'EXHAUSTED')

    def test_not_found_and_bad_image_are_not_retried(self):
        for send in (lambda n: (_ for _ in ()).throw(urllib.error.HTTPError('https://x/1',404,'missing',{},None)),lambda n:Reply(b'not an image')):
            with self.subTest(send=send):
                result,starts,_=self.run_fake(send);self.assertEqual(len(starts),1);self.assertIn('error',result['https://x/1'])

    def test_http_date_retry_after_and_shared_host_cooldown(self):
        def send(n):
            if n==1:raise urllib.error.HTTPError('https://x/1',429,'slow',{'Retry-After':'Thu, 01 Jan 1970 00:16:50 GMT'},None)
            return Reply(png())
        result,starts,_=self.run_fake(send,urls=['https://x/1','https://x/2'])
        self.assertEqual(starts,[1000.,1010.,1011.]);self.assertTrue(all('path' in r for r in result.values()))

    def test_long_retry_after_does_not_retry_early_or_fetch_sibling(self):
        def send(n):raise urllib.error.HTTPError('https://x/1',429,'slow',{'Retry-After':'120'},None)
        result,starts,_=self.run_fake(send,urls=['https://x/1','https://x/2'])
        self.assertEqual(starts,[1000.]);self.assertTrue(all(r['retry_status']=='WAIT_REQUIRED' for r in result.values()))
        self.assertEqual(result['https://x/1']['retry_not_before'],1120.)

    def test_reused_success_never_fetched_and_failed_url_is_retried(self):
        with tempfile.TemporaryDirectory() as root:
            download_unique(['https://x/ok'],root,lambda url,p:Path(p).write_bytes(b'sealed'))
            calls=[]
            def download(url,p):
                calls.append(url)
                if len(calls)==1:raise TimeoutError('timeout')
                Path(p).write_bytes(b'recovered')
            with patch('mye_c_automation.download_manager.time.sleep'):
                result=download_unique(['https://x/ok','https://x/bad'],root,download,reuse_successful=True,max_retries=1,retry_base_seconds=0)
            self.assertTrue(result['https://x/ok']['cached']);self.assertEqual(calls,['https://x/bad','https://x/bad'])

    def test_formal_v2_loads_config_and_freezes_download_receipts(self):
        from mye_c_automation.configuration import initialize_config
        from mye_c_automation.full_product_audit import download_only
        import os
        class Reader:
            def current_shop(self):return 7
            def product(self,pid):return dict(id=pid,images={'main':['https://x/1']})
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);initialize_config(root/'local');config=root/'local/download.local.json'
            self.assertTrue(config.is_file());value=json.loads(config.read_text());self.assertEqual(value['max_retries'],3)
            value['max_retries']=1;value['retry_base_seconds']=0;config.write_text(json.dumps(value))
            with patch.dict(os.environ,{'MYEC_CONFIG_DIR':str(root/'local')}),patch('mye_c_automation.download_manager.urllib.request.urlopen',side_effect=[TimeoutError('timeout'),Reply(png())]):
                result=download_only(5094,7,output_dir=root/'jobs/JOB_new',site=Reader())
            self.assertNotIn('error',result['images'][0])
            receipt=json.loads((root/'jobs/JOB_new/download_results.json').read_text())
            self.assertEqual(receipt['metrics']['network_attempts'],2)
            self.assertEqual(receipt['options']['max_retries'],1)

    def test_invalid_retry_configuration_rejected_before_network(self):
        with tempfile.TemporaryDirectory() as root,patch('mye_c_automation.download_manager.urllib.request.urlopen') as send:
            for value in (-1,True,11,'3'):
                with self.subTest(value=value),self.assertRaises(ValueError):download_unique(['https://x/1'],root,max_retries=value)
            send.assert_not_called()

    def test_long_server_cooldown_survives_next_download_invocation(self):
        with tempfile.TemporaryDirectory() as root,patch('mye_c_automation.download_manager.time.time',return_value=1000.),patch('mye_c_automation.download_manager.urllib.request.urlopen',side_effect=urllib.error.HTTPError('https://x/1',429,'slow',{'Retry-After':'120'},None)) as send:
            first=download_unique(['https://x/1'],root,max_retries=3)
            second=download_unique(['https://x/2'],root,max_retries=3)
            self.assertEqual(send.call_count,1)
            self.assertEqual(second['https://x/2']['retry_not_before'],1120.)
