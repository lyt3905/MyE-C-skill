"""Exercise real multipart construction with browser-copied backend URLs."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from PIL import Image
from mye_c_automation.site_client import _SiteTransport


class UploadBaseJoinTests(unittest.TestCase):
    def test_upload_accepts_trailing_slash_and_preserves_base_path(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / 'candidate.png'
            Image.new('RGB', (32, 32), 'white').save(image)
            image_bytes = image.read_bytes()
            for base, expected in (
                ('https://example.invalid/', 'https://example.invalid/api/admin/uploads/images'),
                ('https://example.invalid/app/', 'https://example.invalid/app/api/admin/uploads/images'),
                ('https://example.invalid', 'https://example.invalid/api/admin/uploads/images'),
            ):
                with self.subTest(base=base):
                    transport = object.__new__(_SiteTransport)
                    transport.cfg = {'base': base}
                    transport.op = MagicMock()
                    transport.op.open.return_value.__enter__.return_value.read.return_value = (
                        b'{"data":{"url":"https://images.invalid/candidate.png"}}'
                    )
                    self.assertEqual(transport.upload(image), 'https://images.invalid/candidate.png')
                    transport.op.open.assert_called_once()
                    request = transport.op.open.call_args.args[0]
                    self.assertEqual(request.full_url, expected)
                    self.assertEqual(request.get_method(), 'POST')
                    self.assertIn(b'Content-Type: image/png\r\n', request.data)
                    self.assertIn(image_bytes, request.data)
                    self.assertEqual(transport.op.open.call_args.kwargs['timeout'], 180)
                    self.assertEqual(transport.cfg['base'], base)
