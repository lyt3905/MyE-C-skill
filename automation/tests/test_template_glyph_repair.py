import copy
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from test_v2_vision import observation


def fixture():
    image = np.zeros((240, 320, 3), np.uint8)
    image[115:170, 120:270] = (170, 170, 170)
    stencil = np.zeros((35, 100), np.uint8)
    cv2.putText(stencil, 'GCC', (4, 25), cv2.FONT_HERSHEY_SIMPLEX, .7, 255, 2)
    for x, y in ((20, 25), (145, 125)):
        roi = image[y:y+35, x:x+100]
        roi[stencil>0] = (roi[stencil>0].astype(float)*.5 + np.array([140, 50, 90])*.5).astype(np.uint8)
    item = dict(id='I', sha256='a'*64, image_type='MAIN', evidence_ids=['S'])
    template = [20/320, 25/240, 120/320, 60/240]
    marks = [dict(kind='STORE_WATERMARK', action='REMOVE_TEXT', owner='THIRD_PARTY_STORE',
        confidence=.2, bbox=box, preserve_overlap_risk='HIGH', repair_mode='TEMPLATE_GLYPHS',
        glyph_template_bbox=template) for box in ([.04,.08,.4,.28],[.4,.48,.85,.74])]
    return image, observation(item, 'REMOVE_TEXT', watermarks=marks), item


class TemplateGlyphTests(unittest.TestCase):
    def test_json_schema_requires_template_only_for_template_mode(self):
        from mye_c_automation.resources import validate_resource_json
        _,value,_=fixture()
        validate_resource_json(value,'image-action-decision.v2.schema.json')
        changed=copy.deepcopy(value);changed['watermarks'][0].pop('glyph_template_bbox')
        with self.assertRaises(ValueError):validate_resource_json(changed,'image-action-decision.v2.schema.json')
        changed=copy.deepcopy(value);changed['watermarks'][0]['repair_mode']='REGION'
        with self.assertRaises(ValueError):validate_resource_json(changed,'image-action-decision.v2.schema.json')

    def test_opencv_fallback_is_not_used_for_product_crossing_glyphs(self):
        from mye_c_automation.image_repairs_v2 import remove_text
        image,value,_=fixture()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source.png';Image.fromarray(image).save(source)
            with self.assertRaisesRegex(ValueError,'GLYPH_REQUIRES_LAMA'):
                remove_text(source,value,root/'out',rights='OWNED_OR_LICENSED',algorithm='OPENCV_NS')

    def test_multiple_possible_copies_in_one_region_are_ambiguous(self):
        from mye_c_automation.image_repairs_v2 import mask_for
        image,value,_=fixture()
        image[180:215,145:245]=image[125:160,145:245]
        value['watermarks'][1]['bbox']=[.4,.48,.85,.99]
        with self.assertRaisesRegex(ValueError,'GLYPH_MATCH_AMBIGUOUS'):
            mask_for((320,240),value,image=image)

    def test_native_fake_pipeline_and_explicit_quality_failure(self):
        from unittest.mock import patch
        from test_v2_workflow import V2WorkflowTests
        image,value,_=fixture()
        def transform(row,item):
            if row['decision']=='REMOVE_TEXT':row['watermarks']=copy.deepcopy(value['watermarks'])
            return row
        def fake_lama(pixels,mask):pixels[mask>0]=0;return pixels
        for quality_fail in (False,True):
            with self.subTest(quality_fail=quality_fail),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);source=root/'watermarked.png';Image.fromarray(image).save(source)
                model=root/'fake.pt';model.write_bytes(b'explicit fake backend, not real model weights')
                with patch('mye_c_automation.image_repairs_v2.lama_torchscript',return_value=fake_lama):
                    result=V2WorkflowTests().scenario(root,['REMOVE_TEXT','KEEP'],
                        asset_images={0:source},observation_transform=transform,
                        image_options={'lama_model_path':str(model)},quality_fail=quality_fail)
                if quality_fail:
                    self.assertEqual(result['writer'].uploads,0)
                    self.assertEqual(result['product']['images']['main'][0],result['original']['images']['main'][0])
                else:
                    self.assertEqual(result['writer'].uploads,1)
                    self.assertEqual(result['writer'].saves,1)
                    self.assertTrue(result['result']['content_validation']['ok'])

    def test_contract_accepts_real_high_risk_without_lowering_score(self):
        from mye_c_automation.ai_judge.image_action_decision import validate
        _, value, item = fixture()
        self.assertEqual(validate(value, item), value)
        for bad in (None, [0,0,0,1], [-.1,0,.2,.3]):
            changed = copy.deepcopy(value); changed['watermarks'][0]['glyph_template_bbox'] = bad
            with self.assertRaises(ValueError): validate(changed, item)

    def test_strokes_cross_foreground_without_rectangular_erasure(self):
        from mye_c_automation.image_repairs_v2 import mask_for
        image, value, _ = fixture()
        mask, ratio = mask_for((320,240), value, image=image, dilation=0)
        self.assertGreater(np.count_nonzero(mask[125:160,145:245]), 50)
        self.assertEqual(mask[130, 240], 0)
        self.assertEqual(mask[180, 180], 0)
        self.assertLess(ratio, .05)
        with self.assertRaises(ValueError):mask_for((320,240), value, image=None)

    def test_protected_print_overlap_is_rejected_not_clipped(self):
        from mye_c_automation.image_repairs_v2 import mask_for
        image, value, _ = fixture()
        value['preserve_regions'] = [dict(kind='PRODUCT_PRINT', bbox=[.4,.48,.85,.74])]
        with self.assertRaisesRegex(ValueError,'PROTECTED_REGION_OVERLAP'):
            mask_for((320,240), value, image=image)

    def test_missing_target_and_busy_template_are_rejected(self):
        from mye_c_automation.image_repairs_v2 import mask_for
        image, value, _ = fixture()
        image[125:160,145:245] = 170
        with self.assertRaises(ValueError):mask_for((320,240), value, image=image)
        image, value, _ = fixture()
        image[25:60,20:120] = np.random.default_rng(8).integers(0,255,(35,100,3),dtype=np.uint8)
        with self.assertRaises(ValueError):mask_for((320,240), value, image=image)

    def test_template_mode_uses_lama_and_preserves_original_and_outside_pixels(self):
        from mye_c_automation.image_repairs_v2 import remove_text, deterministic_quality
        image, value, _ = fixture()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); source=root/'source.png';Image.fromarray(image).save(source)
            original=source.read_bytes(); calls=[]
            def lama(pixels, mask):
                calls.append(True); pixels[mask>0] = (0,0,0); return pixels
            result=remove_text(source,value,root/'repair',rights='OWNED_OR_LICENSED',lama=lama)
            self.assertEqual(result['algorithm'],'LAMA_INPAINT');self.assertEqual(calls,[True])
            self.assertEqual(len(result['template_geometry']),2)
            self.assertTrue(all(p['semantic_classification'] is False for p in result['template_geometry']))
            self.assertEqual(source.read_bytes(),original)
            self.assertTrue(deterministic_quality(source,result['output_path'],result['mask_path'])['ok'])
