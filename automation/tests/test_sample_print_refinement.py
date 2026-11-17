import copy
import json
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from test_global_watermark_flow import global_observation

FIXTURES=Path(__file__).parent/'fixtures/global_glyphs'


class SamplePrintTests(unittest.TestCase):
    def test_actual_robot_sample_recovers_without_modifying_observation(self):
        from mye_c_automation.template_glyphs import repeated_template_strokes
        image=np.array(Image.open(FIXTURES/'5173-main2.webp').convert('RGB'))
        observation=json.loads((FIXTURES/'5173-main2-observation.json').read_text())['original_observation']
        mark=observation['watermarks'][0];before=copy.deepcopy(mark);proof={}
        mask=repeated_template_strokes(image,mark,proof=proof)
        self.assertGreater(np.count_nonzero(mask),500)
        self.assertGreaterEqual(len(proof['matches']),3)
        self.assertTrue(proof['sample_foreground_complete'])
        self.assertEqual(mark,before)

    def test_actual_car_true_ink_stays_protected_until_explicit_restore(self):
        from mye_c_automation.image_repairs_v2 import mask_for
        image=np.array(Image.open(FIXTURES/'5173-main3.webp').convert('RGB'))
        o=json.loads((FIXTURES/'5173-main3-observation.json').read_text())['original_observation']
        for row in o['preserve_regions']:
            if row['kind']=='manufacturer_model_name_JEZZY':row['scope']='BRIGHT_PRINT_GLYPHS'
        for row in o['watermarks']:
            if row.get('action')=='KEEP' and row['kind']=='MODEL_TEXT':row['preserve_mode']='BRIGHT_PRINT_GLYPHS'
        # Complete sample recovery also reaches real Y-edge pixels above the
        # old rectangular box. Bright protection must reject that true overlap.
        with self.assertRaisesRegex(ValueError,'PROTECTED_REGION_OVERLAP'):mask_for((800,800),o,image=image)
        for row in o['preserve_regions']:
            if row['kind'] in {'manufacturer_model_name_JEZZY','product_side_print_number_and_logo','product_hood_print_number'}:row['scope']='PRINT_RESTORE'
        for row in o['watermarks']:
            if row.get('preserve_mode')=='BRIGHT_PRINT_GLYPHS' or row.get('action')=='KEEP' and row['kind']=='PRODUCT_PRINT':row['preserve_mode']='PRINT_RESTORE'
        proof=[];mask,ratio=mask_for((800,800),o,image=image,protection_geometry=proof)
        self.assertGreater(ratio,0);self.assertLess(ratio,.25)
        self.assertTrue(any(p.get('mode')=='PRINT_RESTORE' and p['restore_pixels']>0 for p in proof))

    def test_confirmed_alternate_sample_can_replace_busy_primary(self):
        from mye_c_automation.template_glyphs import repeated_template_strokes
        image,o,_=global_observation();mark=o['watermarks'][0]
        image[25:60,20:120]=np.random.default_rng(9).integers(0,255,(35,100,3),dtype=np.uint8)
        mark['glyph_template_candidates']=[[145/320,125/240,245/320,160/240]]
        proof={};repeated_template_strokes(image,mark,proof=proof)
        self.assertEqual(proof['selected_template_index'],1)

    def test_print_glyph_scope_protects_actual_white_ink_not_entire_rectangle(self):
        from mye_c_automation.image_repairs_v2 import mask_for
        image,o,_=global_observation();cv2.putText(image,'Y',(250,175),cv2.FONT_HERSHEY_SIMPLEX,1,(255,255,255),2)
        region=dict(kind='factory_print',bbox=[.35,.45,.95,.85],scope='BRIGHT_PRINT_GLYPHS')
        o['preserve_regions']=[region];mask,_=mask_for((320,240),o,image=image)
        white=(image.min(axis=2)>230);self.assertFalse(np.any(mask[white]))
        self.assertGreater(np.count_nonzero(mask[125:160,145:245]),50)
        region['scope']='EXACT_REGION'
        with self.assertRaisesRegex(ValueError,'PROTECTED_REGION_OVERLAP'):mask_for((320,240),o,image=image)

    def test_unresolved_bright_print_is_not_empty_protection(self):
        from mye_c_automation.image_repairs_v2 import mask_for
        image,o,_=global_observation();o['preserve_regions']=[dict(kind='print',bbox=[0,.8,.2,1],scope='BRIGHT_PRINT_GLYPHS')]
        with self.assertRaisesRegex(ValueError,'PRINT_GLYPHS_UNRESOLVED'):mask_for((320,240),o,image=image)

    def test_small_print_restore_is_explicit_precise_and_area_bounded(self):
        from mye_c_automation.image_repairs_v2 import mask_for
        image,o,_=global_observation();guard=dict(kind='covered_print',bbox=[.30,.35,.98,.95],scope='PRINT_RESTORE');o['preserve_regions']=[guard]
        proof=[];mask,_=mask_for((320,240),o,image=image,protection_geometry=proof)
        self.assertTrue(any(p.get('restore_pixels',0)>0 for p in proof))
        guard['bbox']=[.45,.52,.65,.68]
        with self.assertRaisesRegex(ValueError,'PRINT_RESTORE_AREA'):mask_for((320,240),o,image=image)
        guard['bbox']=[.30,.35,.98,.95];o['watermarks'][0].update(repair_mode='REGION',preserve_overlap_risk='LOW',bbox=[.4,.48,.85,.74])
        o['watermarks'][0].pop('glyph_search_scope');o['watermarks'][0].pop('glyph_template_bbox')
        with self.assertRaisesRegex(ValueError,'PRINT_RESTORE_REQUIRES_GLYPHS'):mask_for((320,240),o,image=image)

    def test_contract_scopes_and_alternates_require_explicit_matching_modes(self):
        from mye_c_automation.ai_judge.image_action_decision import validate
        from mye_c_automation.resources import validate_resource_json
        _,o,item=global_observation();o['preserve_regions']=[dict(kind='factory',bbox=[.4,.5,.9,.9],scope='BRIGHT_PRINT_GLYPHS')]
        o['watermarks'][0]['glyph_template_candidates']=[[.1,.1,.3,.3]]
        validate(o,item);validate_resource_json(o,'image-action-decision.v2.schema.json')
        o['watermarks'][0]['glyph_template_candidates']=[[-.1,0,.3,.3]]
        with self.assertRaises(ValueError):validate(o,item)
        o['watermarks'][0].pop('glyph_template_candidates');o['watermarks'][0]['preserve_mode']='PRINT_RESTORE'
        with self.assertRaises(ValueError):validate(o,item)

    def test_fake_native_print_restore_still_requires_quality_pass(self):
        from unittest.mock import patch
        from test_v2_workflow import V2WorkflowTests
        image,o,_=global_observation()
        def transform(row,item):
            if row['decision']=='REMOVE_TEXT':
                row['watermarks']=copy.deepcopy(o['watermarks'])
                row['preserve_regions']=[dict(kind='covered_print',bbox=[.30,.35,.98,.95],scope='PRINT_RESTORE')]
            return row
        def backend(pixels,mask):pixels[mask>0]=0;return pixels
        for failure in (False,'identity'):
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);source=root/'source.png';Image.fromarray(image).save(source);model=root/'fake.pt';model.write_bytes(b'fake only')
                with patch('mye_c_automation.image_repairs_v2.lama_torchscript',return_value=backend):
                    s=V2WorkflowTests().scenario(root,['REMOVE_TEXT','KEEP'],asset_images={0:source},
                        observation_transform=transform,image_options={'lama_model_path':str(model)},quality_fail=failure)
                self.assertEqual(s['writer'].uploads,0 if failure else 1)
                if not failure:self.assertTrue(s['result']['content_validation']['ok'])
