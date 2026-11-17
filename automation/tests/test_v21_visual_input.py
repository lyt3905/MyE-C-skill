import unittest,tempfile,hashlib,io
from pathlib import Path
from PIL import Image
from mye_c_automation.ai_judge.client import prepare_image
class VisualInputTests(unittest.TestCase):
 def test_formats_trace_to_unchanged_original(self):
  with tempfile.TemporaryDirectory() as root:
   for fmt in ('JPEG','PNG','WEBP'):
    path=Path(root)/(fmt+'.bin');Image.new('RGB',(31,29),'red').save(path,format=fmt)
    before=path.read_bytes();sent,meta=prepare_image(path)
    self.assertEqual(before,path.read_bytes())
    self.assertEqual(meta['original_sha256'],hashlib.sha256(before).hexdigest())
    self.assertEqual(meta['sent_sha256'],hashlib.sha256(sent).hexdigest())
    self.assertEqual((meta['width'],meta['height']),(31,29))
    self.assertEqual(meta['original_format'],fmt)
    self.assertEqual(Image.open(io.BytesIO(sent)).format,'JPEG')
    self.assertEqual(meta['mime'],'image/jpeg')
