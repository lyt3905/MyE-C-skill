import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

FIX=Path(__file__).parent/'fixtures/global_glyphs'


class KnownResidualTests(unittest.TestCase):
    def test_two_aligned_fragments_catch_robot_partial_false_pass(self):
        from mye_c_automation.image_repairs_v2 import known_pattern_residuals
        original=json.loads((FIX/'5173-main2-observation.json').read_text())['original_observation']
        # The fresh AI selected another clean copy of the identical pattern.
        original['watermarks'][0]['glyph_template_bbox']=[.73,.19,.96,.32]
        guard=known_pattern_residuals(FIX/'5173-main2.webp',FIX/'5173-main2-partial-false-pass.png',original)
        self.assertEqual(guard['status'],'REMAINS')
        matches=[m for p in guard['patterns'] for m in p['matches']]
        self.assertTrue(any(m['method']=='ALIGNED_SOURCE_STROKE_FRAGMENTS' and abs(m['bbox_pixels'][0]-275)<=2 and abs(m['bbox_pixels'][1]-82)<=2 for m in matches),matches)

    def test_same_pattern_retry_keeps_original_and_rejects_identity_failure(self):
        from copy import deepcopy
        from mye_c_automation.ai_judge.image_quality_v2 import residual_observation, CHECKS
        original=json.loads((FIX/'5173-main3-observation.json').read_text())['original_observation']
        before=deepcopy(original)
        row=dict(decision='MATCH',abstain=False,checks={k:True for k in CHECKS},residual_watermarks=[])
        checked=dict(judgement=dict(results=[row]),pixel_residual_guard=dict(status='REMAINS'))
        derived=residual_observation(original,checked)
        self.assertIsNotNone(derived)
        self.assertTrue(all(m.get('glyph_template_source')=='ORIGINAL' for m in derived['watermarks'] if m['action']=='REMOVE_TEXT'))
        self.assertEqual(original,before)
        for flag in CHECKS-{'overlay_removed'}:
            with self.subTest(flag=flag):
                row['checks'][flag]=False
                self.assertIsNone(residual_observation(original,checked))
                row['checks'][flag]=True
        row['abstain']=True
        self.assertIsNone(residual_observation(original,checked))

    def test_source_pattern_does_not_match_blank_or_smooth_coloured_panels(self):
        from mye_c_automation.image_repairs_v2 import known_pattern_residuals
        observation=json.loads((FIX/'5173-main3-observation.json').read_text())['original_observation']
        with tempfile.TemporaryDirectory() as directory:
            for name,image in [('blank',np.zeros((800,800,3),dtype=np.uint8)),('panels',np.repeat(np.arange(800,dtype=np.uint8)[None,:,None],800,axis=0).repeat(3,axis=2))]:
                path=Path(directory)/(name+'.png');Image.fromarray(image).save(path)
                guard=known_pattern_residuals(FIX/'5173-main3.webp',path,observation)
                self.assertEqual(guard['status'],'NO_MATCH',guard)

    def test_source_approved_strokes_find_real_residuals_over_coloured_product(self):
        from mye_c_automation.template_glyphs import repeated_template_strokes
        source=np.array(Image.open(FIX/'5173-main3.webp').convert('RGB'))
        candidate=np.array(Image.open(FIX/'5173-main3-false-pass.png').convert('RGB'))
        observation=json.loads((FIX/'5173-main3-observation.json').read_text())['original_observation']
        mark=dict(observation['watermarks'][0],glyph_template_source='ORIGINAL');proof={}
        repeated_template_strokes(candidate,mark,template_image=source,proof=proof)
        positions=[m['bbox_pixels'][:2] for m in proof['matches']]
        for x,y in ((40,532),(249,445),(406,296)):
            self.assertTrue(any(abs(a-x)<=3 and abs(b-y)<=3 for a,b in positions),positions)
        self.assertFalse(any(abs(a-25)<=3 and abs(b-465)<=3 for a,b in positions))

    def test_pixel_residue_cannot_be_overridden_by_raw_model_pass(self):
        from mye_c_automation.visual_quality import VisualQualityInspector
        from mye_c_automation.ai_judge.client import JudgeClient
        from mye_c_automation.budget_manager import BudgetManager
        source=FIX/'5173-main3.webp';candidate=FIX/'5173-main3-false-pass.png'
        observation=json.loads((FIX/'5173-main3-observation.json').read_text())['original_observation']
        def response(model,item,context):
            row=dict(task_type='image_quality_v2',item_id=item['id'],decision='MATCH',confidence=.99,abstain=False,
                evidence_ids=item['evidence_ids'],checks={k:True for k in ('identity_preserved','packaging_preserved','protected_print_preserved','overlay_removed','no_new_artifacts')},residual_watermarks=[])
            return dict(choices=[dict(message=dict(content=json.dumps(row)))],usage=dict(prompt_tokens=1,completion_tokens=1,total_tokens=2))
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);budget=BudgetManager(dict(ai_requests=2,full_resolution_images=20))
            try:
                client=JudgeClient(budget,root/'cache',transport=response,models=('deepseek-v4.1-flash',),retries=0)
                inspector=VisualQualityInspector(root,dict(budget={}),judge=client)
                checked=inspector.inspect_v2(source,candidate,dict(pid=5173),'REMOVE_TEXT',observation=observation)
                self.assertFalse(checked['ok'])
                self.assertEqual(checked['quality_status'],'FAIL_WATERMARK_REMAINS')
                self.assertEqual(checked['judgement']['results'][0]['decision'],'MATCH')
                self.assertEqual(checked['pixel_residual_guard']['status'],'REMAINS')
            finally:budget.close()

    def test_uniform_pixel_background_does_not_keep_inpaint_speckles(self):
        from test_global_watermark_flow import global_observation
        from mye_c_automation.image_repairs_v2 import remove_text
        image,observation,_=global_observation()
        def backend(pixels,mask):pixels[mask>0]=255;return pixels
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source.png';Image.fromarray(image).save(source)
            repair=remove_text(source,observation,root/'out',rights='OWNED_OR_LICENSED',lama=backend)
            output=np.array(Image.open(repair['output_path']));mask=np.array(Image.open(repair['mask_path']))>0
            background=np.all(image==0,axis=2)&mask
            self.assertTrue(np.any(background))
            self.assertTrue(np.all(output[background]==0))
            self.assertGreater(repair['uniform_background_components'],0)
