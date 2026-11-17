import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image


class RepairBeforeReviewTests(unittest.TestCase):
    def trial(self,root):
        from watermark_module_fixtures import sample
        value=sample(root,boxes=[[.43,.36,.53,.43]],complexity='COMPLEX')
        value['watermarks'][0].update(preserve_overlap_risk='HIGH',subject_overlap=True)
        return value

    def test_existing_schema_and_business_contract_accept_record_only_overlap(self):
        from test_v2_vision import observation
        from mye_c_automation.ai_judge.schemas import validate_result
        item=dict(id='TRIAL',sha256='a'*64,image_type='MAIN',evidence_ids=['SOURCE'])
        for risk in ['LOW','MEDIUM','HIGH']:
            with self.subTest(risk=risk):
                row=observation(item,'REMOVE_TEXT',confidence=0.,watermarks=[dict(kind='STORE_WATERMARK',action='REMOVE_TEXT',
                    bbox=[.43,.36,.53,.43],confidence=0.,preserve_overlap_risk=risk,repair_mode='REGION',subject_overlap=True)])
                validated=validate_result(row,'image_action_decision',item['id'],item)
                self.assertEqual(validated,row)

    def test_no_template_product_overlap_reaches_local_lama_and_preserves_original(self):
        from mye_c_automation.watermark_processing import process_watermarks
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);value=self.trial(root/'input');original=Path(value['image_path']).read_bytes();calls=[]
            def backend(image,mask):calls.append(mask.copy());image[mask>0]=[25,95,160];return image
            result=process_watermarks(value,root/'out',lama=backend)
            self.assertEqual(result['processing_status'],'PROCESSED',result)
            self.assertEqual(result['quality_status'],'PENDING_AI_REVIEW')
            self.assertTrue(calls);self.assertEqual(result['algorithm_used'],['LAMA_INPAINT'])
            self.assertEqual(Path(value['image_path']).read_bytes(),original)
            source=np.array(Image.open(value['image_path']));output=np.array(Image.open(result['output_path']))
            mask=np.array(Image.open(result['mask_paths'][0]));self.assertTrue(np.array_equal(source[mask==0],output[mask==0]))
            self.assertEqual(value['watermarks'][0]['preserve_overlap_risk'],'HIGH')

    def test_fixed_rights_protected_pixels_sha_and_area_still_block_trial(self):
        from mye_c_automation.watermark_processing import process_watermarks
        for mode in ['rights','protected','sha','area','manufacturer']:
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as d:
                root=Path(d);value=self.trial(root/'input');options={}
                if mode=='rights':value['authorization_status']='RIGHTS_UNKNOWN'
                elif mode=='protected':value['preserve_regions'].append(dict(kind='MANUFACTURER_LOGO',bbox=value['watermarks'][0]['bbox']))
                elif mode=='sha':value['image_sha256']='0'*64
                elif mode=='area':options['policy']=dict(max_mask_area=.001)
                else:value['watermarks'][0].update(kind='PRODUCT_PRINT',owner='PRODUCT')
                result=process_watermarks(value,root/'out',lama=lambda *_:self.fail('Fixed protection bypass'),**options)
                self.assertEqual(result['processing_status'],'BLOCKED',result)
                self.assertFalse(result['output_path'])

    def workflow(self,root,quality=False):
        from test_v2_workflow import V2WorkflowTests
        value=self.trial(root/'fixture');model=root/'model.pt';model.write_bytes(b'Fake backend')
        def transform(row,item):
            if row['decision']=='REMOVE_TEXT':
                row.update(watermarks=copy.deepcopy(value['watermarks']),preserve_regions=copy.deepcopy(value['preserve_regions']),background_complexity='COMPLEX')
            return row
        calls=[]
        def backend(image,mask):calls.append(True);image[mask>0]=[25,95,160];return image
        with patch('mye_c_automation.image_repairs_v2.lama_torchscript',return_value=backend):
            result=V2WorkflowTests().scenario(root,['REMOVE_TEXT','KEEP'],asset_images={0:value['image_path']},
                observation_transform=transform,image_options=dict(lama_model_path=str(model)),quality_fail=quality)
        return result,calls

    def test_high_overlap_only_publishes_after_actual_candidate_review(self):
        with tempfile.TemporaryDirectory() as d:
            result,calls=self.workflow(Path(d))
            self.assertTrue(calls)
            self.assertEqual(result['calls'].count('image_quality_v2'),1)
            self.assertEqual(result['writer'].uploads,1)
            self.assertTrue(result['result']['content_validation']['ok'])

    def test_actual_identity_damage_stops_after_candidate_review_without_upload(self):
        with tempfile.TemporaryDirectory() as d:
            result,calls=self.workflow(Path(d),quality='identity')
            self.assertTrue(calls)
            self.assertEqual(result['calls'].count('image_quality_v2'),1)
            self.assertEqual(result['writer'].uploads,0)
            self.assertEqual(result['product']['images']['main'],result['original']['images']['main'])

    def test_actual_remaining_watermark_has_bounded_attempts_and_no_false_success(self):
        with tempfile.TemporaryDirectory() as d:
            result,calls=self.workflow(Path(d),quality=True)
            self.assertTrue(calls)
            self.assertGreaterEqual(result['calls'].count('image_quality_v2'),1)
            self.assertLessEqual(len(calls),2)
            self.assertEqual(result['writer'].uploads,0)

    def test_old_review_is_not_rewritten_as_a_trial(self):
        from test_v2_vision import observation
        from mye_c_automation.ai_judge.image_action_decision import apply_visual_rules
        item=dict(id='OLD',sha256='b'*64,image_type='MAIN',evidence_ids=['SOURCE'])
        old=observation(item,'REVIEW',watermarks=[dict(kind='STORE_WATERMARK',action='REMOVE_TEXT',bbox=[.1,.1,.2,.2],
            confidence=.1,preserve_overlap_risk='HIGH',repair_mode='REGION')])
        snapshot=copy.deepcopy(old);result,changes=apply_visual_rules(old)
        self.assertEqual(old,snapshot);self.assertEqual(result['decision'],'REVIEW');self.assertEqual(changes,[])
