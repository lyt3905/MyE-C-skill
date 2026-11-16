import io,tempfile,unittest,urllib.error
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from mye_c_automation.download_manager import download_unique
from mye_c_automation.executor.site_write_client import SiteWriteClient
from mye_c_automation.site_client import UA,_SiteTransport

def image_bytes():
    data=io.BytesIO();Image.new('RGB',(8,8),'red').save(data,format='PNG');return data.getvalue()

class Reply(io.BytesIO):headers={'Content-Type':'image/png'}

class ImageRequestTests(unittest.TestCase):
    def server(self,request,**kwargs):
        # Reproduce the observed cold-CDN behavior: the complete existing UA is accepted.
        self.requests.append(request)
        if request.get_header('User-agent')!=UA:raise urllib.error.HTTPError(request.full_url,429,'client profile rejected',{},None)
        return Reply(image_bytes())

    def setUp(self):self.requests=[]

    def test_cold_download_succeeds_first_attempt_with_existing_complete_profile(self):
        with tempfile.TemporaryDirectory() as tmp,patch('mye_c_automation.download_manager.urllib.request.urlopen',side_effect=self.server):
            metrics={};row=download_unique(['https://image.invalid/a'],tmp,metrics=metrics)['https://image.invalid/a']
            self.assertNotIn('error',row);self.assertEqual(row['path'].read_bytes(),image_bytes())
            self.assertEqual(metrics['network_attempts'],1);self.assertEqual(metrics['retry_attempts'],0)

    def test_independent_readback_uses_same_complete_profile(self):
        with patch('urllib.request.urlopen',side_effect=self.server):
            self.assertEqual(SiteWriteClient(object()).fetch_image('https://image.invalid/a'),image_bytes())
        self.assertEqual(len(self.requests),1)

    def test_all_three_image_paths_share_profile_and_preserve_original_bytes(self):
        site=_SiteTransport.__new__(_SiteTransport)
        with tempfile.TemporaryDirectory() as tmp,patch('urllib.request.urlopen',side_effect=self.server):
            row=download_unique(['https://image.invalid/a'],Path(tmp)/'cache')['https://image.invalid/a']
            fetched=SiteWriteClient(object()).fetch_image('https://image.invalid/a')
            site.download('https://image.invalid/a',str(Path(tmp)/'original.bin'))
            self.assertEqual(row['path'].read_bytes(),fetched);self.assertEqual(fetched,(Path(tmp)/'original.bin').read_bytes())
        self.assertEqual(len(self.requests),3)
        self.assertEqual(len({r.get_header('User-agent') for r in self.requests}),1)
        self.assertEqual(len({r.get_header('Accept') for r in self.requests}),1)
        self.assertEqual(len({r.get_header('Referer') for r in self.requests}),1)

    def test_verified_success_cache_remains_untouched_and_invalid_url_is_not_sent(self):
        with tempfile.TemporaryDirectory() as tmp:
            download_unique(['https://image.invalid/a'],tmp,lambda url,path:Path(path).write_bytes(image_bytes()))
            before={p.name:p.read_bytes() for p in Path(tmp).iterdir()}
            with patch('urllib.request.urlopen',side_effect=AssertionError('cache hit fetched again')):
                row=download_unique(['https://image.invalid/a'],tmp,reuse_successful=True)['https://image.invalid/a'];self.assertTrue(row['cached'])
                with self.assertRaises(ValueError):SiteWriteClient(object()).fetch_image('file:///not-http')
            self.assertEqual(before,{p.name:p.read_bytes() for p in Path(tmp).iterdir()})
