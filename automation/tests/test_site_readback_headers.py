import io
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch
from mye_c_automation.executor.site_write_client import SiteWriteClient


class SiteReadbackHeadersTests(unittest.TestCase):
    def test_readback_uses_same_public_image_headers_as_audit(self):
        def respond(request,timeout):
            if not isinstance(request,urllib.request.Request):
                raise urllib.error.HTTPError(str(request),403,'missing public image headers',{},None)
            self.assertEqual(request.get_header('Referer'),'https://www.aliexpress.com/')
            self.assertIn('Mozilla',request.get_header('User-agent'))
            self.assertIn('image/',request.get_header('Accept'))
            self.assertIsNone(request.get_header('Cookie'))
            self.assertIsNone(request.get_header('Authorization'))
            return io.BytesIO(b'original-image-bytes')
        with patch('urllib.request.urlopen',side_effect=respond):
            self.assertEqual(SiteWriteClient(object()).fetch_image('https://image.example/photo.jpg'),b'original-image-bytes')

    def test_non_http_references_are_rejected_before_fetch(self):
        with patch('urllib.request.urlopen') as fetch:
            with self.assertRaises(ValueError):SiteWriteClient(object()).fetch_image('file:///secret')
            fetch.assert_not_called()
