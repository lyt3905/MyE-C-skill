import copy
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image
from test_template_glyph_repair import fixture


def global_observation():
    image,value,item=fixture()
    value['watermarks']=value['watermarks'][:1]
    value['watermarks'][0]['glyph_search_scope']='IMAGE'
    return image,value,item


class GlobalWatermarkTests(unittest.TestCase):
    def test_real_photo_flat_windows_cannot_be_accepted_as_matching_glyphs(self):
        from mye_c_automation.template_glyphs import repeated_template_strokes,_template_data
        image=np.array(Image.open(Path(__file__).parent/'fixtures/global_glyphs/5173-main2.webp').convert('RGB'))
        mark=dict(glyph_search_scope='IMAGE',glyph_template_bbox=[.735,.17,.985,.28])
        projected,template,_,_=_template_data(image,mark);proof={}
        repeated_template_strokes(image,mark,proof=proof)
        self.assertGreaterEqual(len(proof['matches']),3)
        for match in proof['matches']:
            x0,y0,x1,y1=match['bbox_pixels']
            self.assertGreater(float(projected[y0:y1,x0:x1].std()),0)
            self.assertNotIn((x0,y0),((583,319),(171,328),(618,412),(508,604)))

    def test_erased_sample_can_be_reused_from_original_for_remaining_copy(self):
        from mye_c_automation.image_repairs_v2 import mask_for
        image,value,_=global_observation();candidate=image.copy();candidate[25:60,20:120]=0
        value['watermarks'][0]['glyph_template_source']='ORIGINAL'
        mask,_=mask_for((320,240),value,image=candidate,template_image=image)
        self.assertGreater(np.count_nonzero(mask[125:160,145:245]),50)
        self.assertEqual(np.count_nonzero(mask[25:60,20:120]),0)

    def test_native_global_pipeline_one_review_and_one_bounded_residual_review(self):
        import json
        from unittest.mock import patch
        from mye_c_automation.ai_judge.client import JudgeClient
        from test_v2_workflow import V2WorkflowTests
        classify=JudgeClient.classify
        for supplement in (False,True,'remain'):
            with self.subTest(supplement=supplement),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);image,value,_=global_observation()
                image[195:205,270:290]=(200,0,0)
                source=root/'source.png';Image.fromarray(image).save(source)
                model=root/'fake.pt';model.write_bytes(b'explicit fake weights')
                qualities=[];backend_inputs=[]
                def backend(pixels,mask):backend_inputs.append(pixels.copy());pixels[mask>0]=0;return pixels
                def transform(row,item):
                    if row['decision']=='REMOVE_TEXT':row['watermarks']=copy.deepcopy(value['watermarks'])
                    return row
                def wrapped(client,task,item,context,**kwargs):
                    if task!='image_quality_v2':return classify(client,task,item,context,**kwargs)
                    qualities.append(item['sha256']);transport=client.transport
                    def respond(model,evidence,ctx):
                        flags={k:True for k in ('identity_preserved','packaging_preserved','protected_print_preserved','overlay_removed','no_new_artifacts')}
                        row=dict(task_type=task,item_id=evidence['id'],confidence=.1,abstain=False,decision='MATCH',evidence_ids=evidence['evidence_ids'],checks=flags)
                        if supplement and (len(qualities)==1 or supplement=='remain'):
                            flags['overlay_removed']=False;row['decision']='MISMATCH'
                            row['residual_watermarks']=[dict(kind='STORE_WATERMARK',action='REMOVE_TEXT',bbox=[.82,.79,.94,.89],
                                confidence=.1,preserve_overlap_risk='LOW',repair_mode='REGION')]
                        return dict(choices=[dict(message=dict(content=json.dumps(row)))],usage=dict(prompt_tokens=1,completion_tokens=1,total_tokens=2))
                    client.transport=respond
                    try:return classify(client,task,item,context,**kwargs)
                    finally:client.transport=transport
                with patch.object(JudgeClient,'classify',wrapped),patch('mye_c_automation.image_repairs_v2.lama_torchscript',return_value=backend):
                    result=V2WorkflowTests().scenario(root,['REMOVE_TEXT','KEEP'],asset_images={0:source},
                        observation_transform=transform,image_options={'lama_model_path':str(model)})
                self.assertEqual(len(qualities),2 if supplement else 1)
                self.assertEqual(len(backend_inputs),2 if supplement else 1)
                self.assertTrue(all(np.array_equal(v,backend_inputs[0]) for v in backend_inputs))
                self.assertEqual(result['calls'].count('image_action_decision'),2)
                if supplement=='remain':
                    self.assertEqual(result['writer'].uploads,0)
                    self.assertEqual(result['product']['images']['main'],result['original']['images']['main'])
                else:
                    self.assertEqual(result['writer'].uploads,1);self.assertEqual(result['writer'].saves,1)
                    self.assertTrue(result['result']['content_validation']['ok'])

    def test_validated_model_cache_rebinds_new_job_ids_without_new_request(self):
        import json,hashlib
        from mye_c_automation.ai_judge.client import JudgeClient
        from mye_c_automation.ai_judge.image_action_decision import decide
        from mye_c_automation.budget_manager import BudgetManager
        from test_v2_vision import observation
        calls=[]
        def transport(model,item,context):
            calls.append(True)
            return dict(choices=[dict(message=dict(content=json.dumps(observation(item))))],usage=dict(prompt_tokens=1,completion_tokens=1,total_tokens=2))
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source.png';Image.fromarray(fixture()[0]).save(source)
            digest=hashlib.sha256(source.read_bytes()).hexdigest()
            for label in ('old','new'):
                budget=BudgetManager(dict(ai_requests=2,full_resolution_images=2))
                try:
                    client=JudgeClient(budget,root/'cache',transport=transport,models=('deepseek-v4.1-flash',),retries=0)
                    item=dict(id=label,task_type='image_action_decision',local=str(source),sha256=digest,image_type='MAIN',evidence_ids=[label])
                    result=decide(client,item,dict(pid=1,shop=7))
                    self.assertEqual(result['observation']['item_id'],label)
                    self.assertEqual(result['observation']['evidence_ids'],[label])
                    if label=='new':self.assertEqual(client.metrics['requests'],0)
                finally:budget.close()
            self.assertEqual(len(calls),1)

    def test_residual_helper_preserves_legacy_protection_and_stops_other_failures(self):
        from mye_c_automation.ai_judge.image_quality_v2 import residual_observation
        _,value,_=global_observation()
        protected=dict(kind='MANUFACTURER_LOGO',owner='MANUFACTURER',confidence=.1,preserve_overlap_risk='LOW',bbox=[0,0,.1,.1])
        value['watermarks'].append(protected);before=copy.deepcopy(value)
        flags=dict(identity_preserved=True,packaging_preserved=True,protected_print_preserved=True,overlay_removed=False,no_new_artifacts=True)
        row=dict(decision='MISMATCH',abstain=False,checks=flags,residual_watermarks=global_observation()[1]['watermarks'])
        quality=dict(judgement=dict(results=[row]))
        result=residual_observation(value,quality)
        self.assertIn(protected,result['watermarks']);self.assertEqual(value,before)
        for changes in (dict(abstain=True),dict(decision='UNCERTAIN'),dict(checks=dict(flags,identity_preserved=False)),dict(residual_watermarks=[])):
            self.assertIsNone(residual_observation(value,dict(judgement=dict(results=[dict(row,**changes)]))))

    def test_global_opt_in_finds_unlisted_copy_and_protects_print(self):
        from mye_c_automation.ai_judge.image_action_decision import validate
        from mye_c_automation.image_repairs_v2 import mask_for
        image,value,item=global_observation();self.assertEqual(validate(value,item),value)
        geometry=[];mask,_=mask_for((320,240),value,image=image,geometry=geometry)
        self.assertGreater(np.count_nonzero(mask[125:160,145:245]),50)
        self.assertEqual(len(geometry[0]['matches']),2)
        value['preserve_regions']=[dict(kind='PRINT',bbox=[.4,.48,.85,.74])]
        with self.assertRaisesRegex(ValueError,'PROTECTED_REGION_OVERLAP'):mask_for((320,240),value,image=image)

    def test_default_region_does_not_silently_search_whole_image(self):
        from mye_c_automation.image_repairs_v2 import mask_for
        image,value,_=global_observation();value['watermarks'][0].pop('glyph_search_scope')
        mask,_=mask_for((320,240),value,image=image)
        self.assertEqual(np.count_nonzero(mask[125:160,145:245]),0)

    def test_image_scope_requires_template_mode(self):
        from mye_c_automation.ai_judge.image_action_decision import validate
        _,value,item=global_observation();value['watermarks'][0]['repair_mode']='REGION'
        with self.assertRaises(ValueError):validate(value,item)

    def test_repair_cache_hit_and_tamper_falls_back_to_backend(self):
        from mye_c_automation.image_repairs_v2 import remove_text
        image,value,_=global_observation();calls=[]
        def lama(pixels,mask):calls.append(True);pixels[mask>0]=0;return pixels
        lama.model_sha256='a'*64
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source.png';Image.fromarray(image).save(source)
            first=remove_text(source,value,root/'one',rights='OWNED_OR_LICENSED',lama=lama,cache_dir=root/'cache')
            second=remove_text(source,value,root/'two',rights='OWNED_OR_LICENSED',lama=lama,cache_dir=root/'cache')
            self.assertEqual(len(calls),1);self.assertTrue(second['cache_hit'])
            self.assertEqual(first['output_sha256'],second['output_sha256'])
            receipt=next((root/'cache').glob('*.json'));receipt.write_text('{}')
            remove_text(source,value,root/'three',rights='OWNED_OR_LICENSED',lama=lama,cache_dir=root/'cache')
            self.assertEqual(len(calls),2)
            lama.model_sha256='b'*64
            remove_text(source,value,root/'four',rights='OWNED_OR_LICENSED',lama=lama,cache_dir=root/'cache')
            self.assertEqual(len(calls),3)

    def test_supplemental_union_inpaints_original_not_candidate(self):
        from mye_c_automation.image_repairs_v2 import remove_text,deterministic_quality
        image,value,_=global_observation();seen=[]
        def lama(pixels,mask):seen.append(pixels.copy());pixels[mask>0]=0;return pixels
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source.png';Image.fromarray(image).save(source)
            first=remove_text(source,value,root/'one',rights='OWNED_OR_LICENSED',lama=lama)
            feedback=copy.deepcopy(value);feedback['watermarks']=[dict(kind='STORE_WATERMARK',action='REMOVE_TEXT',
                preserve_overlap_risk='LOW',bbox=[.8,.8,.9,.9],confidence=.1,repair_mode='REGION')]
            second=remove_text(source,feedback,root/'two',rights='OWNED_OR_LICENSED',lama=lama,algorithm='LAMA_INPAINT',
                mask_source=first['output_path'],prior_mask=first['mask_path'])
            self.assertTrue(np.array_equal(seen[0],seen[1]))
            self.assertTrue(deterministic_quality(source,second['output_path'],second['mask_path'])['ok'])
            self.assertGreater(second['mask_ratio'],first['mask_ratio'])

    def test_residual_feedback_is_optional_but_invalid_or_contradictory_is_rejected(self):
        from mye_c_automation.ai_judge.schemas import validate_result
        row=dict(task_type='image_quality_v2',item_id='Q',decision='MISMATCH',confidence=.1,abstain=False,evidence_ids=['S'],
            checks=dict(identity_preserved=True,packaging_preserved=True,protected_print_preserved=True,overlay_removed=False,no_new_artifacts=True))
        self.assertEqual(validate_result(row,'image_quality_v2','Q'),row)
        changed=dict(row,residual_watermarks=[dict(action='DELETE',bbox=[0,0,1,1])])
        with self.assertRaises(ValueError):validate_result(changed,'image_quality_v2','Q')
        changed=dict(row,residual_watermarks=global_observation()[1]['watermarks'])
        validate_result(changed,'image_quality_v2','Q')
        changed['checks']=dict(row['checks'],overlay_removed=True)
        with self.assertRaises(ValueError):validate_result(changed,'image_quality_v2','Q')
