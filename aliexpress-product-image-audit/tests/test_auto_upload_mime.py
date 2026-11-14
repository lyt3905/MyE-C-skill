import tempfile,unittest
from pathlib import Path
from PIL import Image
from unittest.mock import Mock
from site_client import _SiteTransport

class UploadMimeTests(unittest.TestCase):
    def test_png_upload_advertises_actual_mime(self):
        class Response:
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self):return b'{"data":{"url":"https://fake/upload"}}'
        with tempfile.TemporaryDirectory() as root:
            image=Path(root)/'asset.png';Image.new('RGB',(800,800)).save(image)
            site=object.__new__(_SiteTransport);site.cfg={'base':'https://fake'};site.op=Mock();site.op.open.return_value=Response()
            self.assertEqual(site.upload(image),'https://fake/upload')
            request=site.op.open.call_args.args[0]
            self.assertIn(b'Content-Type: image/png\r\n',request.data)
