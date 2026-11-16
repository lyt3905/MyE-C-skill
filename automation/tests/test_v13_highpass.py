"""Independent localization evidence, never a watermark ownership verdict."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from mye_c_automation.evidence_builder import build
import test_v13_account_cli


class HighpassTests(unittest.TestCase):
    def test_both_polarities_have_independent_bound_highpass(self):
        for background, ink in [(240, 234), (20, 26)]:
            with self.subTest(background=background), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                source = root/'source.png'
                image = Image.new('RGB', (320, 200), (background,)*3)
                ImageDraw.Draw(image).text((30, 70), 'FAINT STORE WATERMARK', fill=(ink,)*3)
                image.save(source)
                original = source.read_bytes()
                build(root, [{'kind':'main','index':0,'file':str(source)}], shop_id=7)
                self.assertNotEqual(hashlib.sha256((root/'highpass_montage.jpg').read_bytes()).hexdigest(),
                                    hashlib.sha256((root/'resid_montage.jpg').read_bytes()).hexdigest())
                manifest = json.loads((root/'highpass_manifest.json').read_text())
                item = manifest['items'][0]
                self.assertEqual(item['source_sha256'], hashlib.sha256(original).hexdigest())
                self.assertGreater(len(item['scales']), 1)
                for scale in item['scales']:
                    for polarity in ('positive', 'negative'):
                        self.assertEqual(scale[polarity+'_sha256'], hashlib.sha256(
                            (root/scale[polarity+'_path']).read_bytes()).hexdigest())
                        with Image.open(root/scale[polarity+'_path']) as band:
                            self.assertEqual(band.size,(320,200))
                            self.assertGreater(np.array(band).max(),0)
                self.assertEqual(original, source.read_bytes())
                self.assertNotIn('classification', item)

    def test_ocr_roi_coordinates_and_bytes_match_original_without_ownership_claim(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); source=root/'source.png'
            array=np.random.default_rng(1).integers(0,256,(100,160,3),dtype=np.uint8)
            Image.fromarray(array).save(source)
            build(root,[{'kind':'sku','index':2,'file':str(source),
                         'ocr':[{'rect':[10,20,70,45], 'score':.95, 'text':'Official Brand'}]}],shop_id=7)
            candidates=json.loads((root/'candidate_crop_manifest.json').read_text())['items']
            roi=next(r for r in candidates if r['algorithm']=='ocr-region/v1')
            self.assertEqual(roi['source_coordinates'],[10,20,70,45])
            self.assertEqual((roi['image_id'],roi['pool'],roi['index']),('SKU_002','sku',2))
            with Image.open(root/roi['path']) as cropped:
                np.testing.assert_array_equal(np.array(cropped),array[20:45,10:70])
            self.assertEqual(roi['sha256'],hashlib.sha256((root/roi['path']).read_bytes()).hexdigest())
            self.assertNotIn('classification',roi)

    def test_flat_image_has_explicit_empty_candidates(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'flat.png';Image.new('RGB',(100,100),'white').save(source)
            build(root,[{'kind':'detail','index':0,'file':str(source)}],shop_id=7)
            result=json.loads((root/'candidate_crop_manifest.json').read_text())
            self.assertEqual(result['items'],[])
            self.assertEqual(result['status'],'NO_CANDIDATES')

    def test_rerun_keeps_old_files_but_excludes_them_from_current_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source.png';Image.new('RGB',(100,100),'white').save(source)
            build(root,[{'kind':'main','index':0,'file':str(source),
                         'ocr':[{'rect':[10,10,30,30],'score':.9}]}],shop_id=7)
            old_crop=next((root/'candidate_crops').glob('*.png'))
            build(root,[],shop_id=7)
            bound={r['path'] for r in json.loads((root/'evidence_manifest.json').read_text())['files']}
            self.assertTrue(old_crop.exists())
            self.assertNotIn(str(old_crop.relative_to(root)),bound)
            self.assertFalse(any(Path(p).suffix=='.png' or 'montage' in p for p in bound))

    def test_missing_indexes_do_not_bind_ocr_from_another_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);rows=[]
            for i,rect in enumerate(([10,10,20,20],[30,30,40,40])):
                source=root/(str(i)+'.png');Image.new('RGB',(100,100),'white').save(source)
                rows.append({'kind':'main','file':str(source),'ocr':[{'rect':rect,'score':.9}]})
            build(root,rows,shop_id=7)
            rois=json.loads((root/'candidate_crop_manifest.json').read_text())['items']
            self.assertEqual({r['image_id']:r['source_coordinates'] for r in rois},
                             {'MAIN_000':[10,10,20,20],'MAIN_001':[30,30,40,40]})

    def test_resized_residual_roi_maps_back_to_original_pixels(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'large.png'
            image=Image.new('RGB',(2000,1200),'gray')
            ImageDraw.Draw(image).rectangle((1200,600,1240,640),fill='white');image.save(source)
            build(root,[{'kind':'main','index':0,'file':str(source)}],shop_id=7)
            rois=json.loads((root/'candidate_crop_manifest.json').read_text())['items']
            covering=[r for r in rois if r['source_coordinates'][0]<=1220<r['source_coordinates'][2]
                      and r['source_coordinates'][1]<=620<r['source_coordinates'][3]]
            self.assertTrue(covering)
            for roi in covering:
                with Image.open(root/roi['path']) as crop:
                    np.testing.assert_array_equal(np.array(crop),np.array(image.crop(roi['source_coordinates'])))

    def test_standard_cli_binds_highpass_and_roi_files_with_fake_writer(self):
        with tempfile.TemporaryDirectory() as temp:
            transport,path,_,error=test_v13_account_cli.AccountCliTests().execute(temp)
            self.assertIsNone(error,repr(error))
            self.assertEqual((transport.uploads,transport.saves),(1,1))
            manifest=json.loads((path/'evidence_manifest.json').read_text())
            files={r['path']:r['sha256'] for r in manifest['files']}
            self.assertIn('highpass_manifest.json',files)
            for row in json.loads((path/'highpass_manifest.json').read_text())['items']:
                for scale in row['scales']:
                    for polarity in ('positive','negative'):
                        self.assertEqual(files[scale[polarity+'_path']],scale[polarity+'_sha256'])
            for row in json.loads((path/'candidate_crop_manifest.json').read_text())['items']:
                self.assertEqual(files[row['path']],row['sha256'])

    def test_standard_cli_rejects_highpass_tamper_after_preview_before_upload(self):
        def tamper(transport,path):
            image=next((path/'highpass').glob('*.png'))
            image.write_bytes(image.read_bytes()+b'changed')
        with tempfile.TemporaryDirectory() as temp:
            transport,_,_,error=test_v13_account_cli.AccountCliTests().execute(temp,after_preview=tamper)
            self.assertIsNotNone(error)
            self.assertEqual((transport.uploads,transport.saves),(0,0))
