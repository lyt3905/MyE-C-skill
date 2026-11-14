import tempfile, unittest, json
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
from evidence_builder import build

class EvidenceIntegration(unittest.TestCase):
    def test_template_and_residual_are_real_outputs(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); source=root/'source.png'
            Image.fromarray(np.random.default_rng(8).integers(0,256,(80,80,3),dtype=np.uint8)).save(source)
            np.save(root/'template.npy',np.ones((8,8),dtype=np.float32))
            with patch('wm_tpl.scan',return_value=.81) as scan:
                build(root,[{'kind':'main','file':str(source),'index':0}],templates=[{'path':'template.npy','shop_id':7}],shop_id=7)
                scan.assert_called_once()
            result=json.loads((root/'template_scan.json').read_text())
            self.assertEqual(result['items'][0]['status'],'HIT')
            self.assertTrue((root/'resid_montage.jpg').exists())
            self.assertTrue((root/'highpass_montage.jpg').exists())
            self.assertEqual(result['items'][0]['std_floor'],2)

if __name__=='__main__': unittest.main()
