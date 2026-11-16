import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
from mye_c_automation import wm_tpl
from mye_c_automation.evidence_builder import build
import test_v13_account_cli


class RoiSourceTests(unittest.TestCase):
    def test_faint_match_variance_uses_the_same_top_left_window_as_ncc(self):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'faint.png'
            gray=np.full((100,140),128,dtype=np.uint8)
            gray[40:48,50:58]=128+(np.indices((8,8)).sum(axis=0)%2*5).astype(np.uint8)
            Image.fromarray(gray).save(source)
            template=wm_tpl.resid(str(source))[40:48,50:58]
            result=wm_tpl.scan(str(source),template,return_location=True)
            self.assertEqual(result['source_coordinates'],[50,40,58,48])
            self.assertGreater(result['ncc'],.999)

    def test_template_hit_retains_exact_original_coordinates_and_template_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'image.png'
            Image.fromarray(np.random.default_rng(71).integers(0,256,(100,140,3),dtype=np.uint8)).save(source)
            before=source.read_bytes();template=root/'template.npy'
            np.save(template,wm_tpl.resid(str(source))[20:32,30:46])
            build(root,[{'kind':'main','index':0,'file':str(source)}],templates=[{'shop_id':7,'path':str(template)}],shop_id=7)
            scan=json.loads((root/'template_scan.json').read_text())['items'][0]
            self.assertEqual(scan['source_coordinates'],[30,20,46,32])
            roi=next(r for r in json.loads((root/'candidate_crop_manifest.json').read_text())['items'] if r['algorithm']=='wm_tpl/v2')
            self.assertEqual(roi['source_coordinates'],[30,20,46,32])
            self.assertEqual(roi['template_sha256'],hashlib.sha256(template.read_bytes()).hexdigest())
            self.assertEqual(roi['source_sha256'],hashlib.sha256(before).hexdigest())
            with Image.open(root/roi['path']) as crop,Image.open(source) as original:
                np.testing.assert_array_equal(np.array(crop),np.array(original)[20:32,30:46])
            self.assertEqual(source.read_bytes(),before)
            self.assertNotIn('classification',roi)

    def test_existing_edge_band_signal_has_traceable_original_roi(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'image.png';Image.new('RGB',(100,80),'white').save(source)
            build(root,[{'kind':'detail','index':2,'file':str(source),'borders':[
                {'side':'bottom','pixels':8,'uniformity':.99,'color':'white'}]}],shop_id=7)
            roi=next(r for r in json.loads((root/'candidate_crop_manifest.json').read_text())['items'] if r['algorithm']=='edge-band/v1')
            self.assertEqual(roi['source_coordinates'],[0,72,100,80])
            self.assertEqual((roi['image_id'],roi['pool'],roi['index']),('DETAIL_002','detail',2))
            self.assertEqual(roi['score'],.99)

    def test_undecodable_template_cli_is_unknown_never_clean(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'bad.jpg';source.write_bytes(b'bad image')
            template=root/'template.npy';np.save(template,np.ones((4,4),dtype=np.float32))
            output=io.StringIO()
            with patch('mye_c_automation.wm_tpl.TPL',str(template)),contextlib.redirect_stdout(output):wm_tpl.main(['scan',str(source)])
            self.assertIn('UNKNOWN',output.getvalue())
            self.assertNotIn('CLEAN',output.getvalue())

    def test_standard_cli_keeps_template_roi_in_bound_evidence_without_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            writer,path,_,error=test_v13_account_cli.AccountCliTests().execute(temp,case='template_localization')
            self.assertIsNone(error,repr(error))
            self.assertEqual((writer.uploads,writer.saves),(0,0))
            rois=json.loads((path/'candidate_crop_manifest.json').read_text())['items']
            roi=next(r for r in rois if r['algorithm']=='wm_tpl/v2' and r['image_id']=='DETAIL_000')
            self.assertEqual(roi['source_coordinates'],[200,300,216,316])
            files={r['path']:r['sha256'] for r in json.loads((path/'evidence_manifest.json').read_text())['files']}
            self.assertEqual(files[roi['path']],roi['sha256'])
