import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
from test_global_watermark_flow import global_observation

def overlap_fixture(directory,*,print_restore=False):
    image,o,_=global_observation()
    o['preserve_regions']=[dict(kind='physical_detail',bbox=[.45,.52,.65,.68],scope='PRINT_RESTORE' if print_restore else 'EXACT_REGION')]
    source=Path(directory)/'source.png';Image.fromarray(image).save(source)
    return source,image,o

class OverlapTrialFlowTests(unittest.TestCase):
    def backend(self,image,mask):image[mask>0]=[13,17,23];return image

    def test_default_product_repair_trials_overlap_and_retains_original_protection(self):
        from mye_c_automation.image_repairs_v2 import remove_text,deterministic_quality
        with tempfile.TemporaryDirectory() as d:
            source,image,o=overlap_fixture(d);before=copy.deepcopy(o);data=source.read_bytes();calls=[]
            def backend(image,mask):calls.append(mask.copy());return self.backend(image,mask)
            result=remove_text(source,o,Path(d)/'out',rights='OWNED_OR_LICENSED',lama=backend)
            self.assertTrue(calls);self.assertTrue(result['protection_overlap_trial'])
            self.assertEqual(result['quality_status'],'PENDING_AI_REVIEW')
            self.assertEqual(result['execution_observation']['preserve_regions'],o['preserve_regions'])
            self.assertGreater(result['protected_region_comparison']['changed_pixels'],0)
            self.assertTrue(deterministic_quality(source,result['output_path'],result['mask_path'])['ok'])
            self.assertEqual(source.read_bytes(),data);self.assertEqual(o,before)

    def test_explicit_strict_policy_still_blocks_before_backend(self):
        from mye_c_automation.image_repairs_v2 import remove_text
        with tempfile.TemporaryDirectory() as d:
            source,_,o=overlap_fixture(d)
            with self.assertRaisesRegex(ValueError,'PROTECTED_REGION_OVERLAP'):
                remove_text(source,o,Path(d)/'out',rights='OWNED_OR_LICENSED',lama=lambda *a:self.fail('Strict overlap reached backend'),
                    processing_policy={'protection_overlap_trial':False})

    def test_print_fraction_limit_is_trial_metadata_but_remains_a_strict_gate(self):
        from mye_c_automation.image_repairs_v2 import remove_text
        with tempfile.TemporaryDirectory() as d:
            source,_,o=overlap_fixture(d,print_restore=True)
            with self.assertRaisesRegex(ValueError,'PRINT_RESTORE_AREA'):
                remove_text(source,o,Path(d)/'strict',rights='OWNED_OR_LICENSED',lama=self.backend,
                    processing_policy={'protection_overlap_trial':False})
            result=remove_text(source,o,Path(d)/'trial',rights='OWNED_OR_LICENSED',lama=self.backend)
            self.assertEqual(result['quality_status'],'PENDING_AI_REVIEW')
            self.assertTrue(any(p.get('restore_fraction',0)>.10 for p in result['print_protection']))

    def test_total_mask_cap_and_rights_still_block_even_with_trial_enabled(self):
        from mye_c_automation.image_repairs_v2 import remove_text
        for mode in ['area','rights']:
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as d:
                source,_,o=overlap_fixture(d)
                with self.assertRaisesRegex(ValueError,'MASK_AREA' if mode=='area' else 'RIGHTS_NOT_AUTHORIZED'):
                    remove_text(source,o,Path(d)/'out',rights='RIGHTS_UNKNOWN' if mode=='rights' else 'OWNED_OR_LICENSED',
                        lama=lambda *a:self.fail('Rejected input reached backend'),processing_policy={'max_mask_area':.001} if mode=='area' else None)

    def test_unresolved_bright_print_does_not_prevent_trial_or_disappear_from_review(self):
        from mye_c_automation.image_repairs_v2 import remove_text
        with tempfile.TemporaryDirectory() as d:
            source,_,o=overlap_fixture(d);o['preserve_regions'][0]['scope']='BRIGHT_PRINT_GLYPHS'
            result=remove_text(source,o,Path(d)/'out',rights='OWNED_OR_LICENSED',lama=self.backend)
            self.assertEqual(result['execution_observation']['preserve_regions'],o['preserve_regions'])
            self.assertTrue(result['protected_region_comparison']['regions'])

    def test_generic_region_path_can_trial_and_retains_mask_receipt(self):
        from mye_c_automation.image_repairs_v2 import remove_text
        with tempfile.TemporaryDirectory() as d:
            source,_,o=overlap_fixture(d)
            for m in o['watermarks']:
                if m.get('action')=='REMOVE_TEXT':
                    m['repair_mode']='REGION'
                    for k in ['glyph_search_scope','glyph_template_bbox','glyph_template_source','glyph_template_candidates']:m.pop(k,None)
            o['preserve_regions'][0]['bbox']=[.06,.10,.35,.30]
            result=remove_text(source,o,Path(d)/'out',rights='OWNED_OR_LICENSED',lama=self.backend,
                processing_policy={'auto_text_masks':False,'prefer_repeated_glyphs':False})
            self.assertTrue(result['protection_overlap_trial']);self.assertTrue(Path(result['module_result_path']).is_file())
            self.assertGreater(result['protected_region_comparison']['changed_pixels'],0)

    def test_actual_quality_sees_unchanged_original_annotations_and_bound_comparison(self):
        from mye_c_automation.image_repairs_v2 import remove_text
        from mye_c_automation.visual_quality import VisualQualityInspector
        class Judge:
            models=('deepseek-v4.1-flash',)
            def classify(inner,task,item,context,**kwargs):
                self.assertEqual(item['repair_observation']['preserve_regions'],o['preserve_regions'])
                self.assertIn('protected_region_comparison',item['reason'])
                self.assertTrue(any(r['image_id']=='PROTECTED_REGIONS' for r in item['extra_images']))
                inner.item=item
                return dict(status='CLEAN',models=list(inner.models),results=[dict(decision='MATCH',abstain=False,
                    checks={k:True for k in ['identity_preserved','packaging_preserved','protected_print_preserved','overlay_removed','no_new_artifacts']})])
        with tempfile.TemporaryDirectory() as d:
            source,_,o=overlap_fixture(d);result=remove_text(source,o,Path(d)/'out',rights='OWNED_OR_LICENSED',lama=self.backend)
            inspector=VisualQualityInspector(Path(d),{'budget':{}},judge=Judge())
            q=inspector.inspect_v2(source,result['output_path'],{},'REMOVE_TEXT',result['mask_path'],observation=result['execution_observation'])
            self.assertTrue(q['ok']);self.assertEqual(q['protection_review_status'],'PASS')
            self.assertEqual(q['protected_region_comparison']['candidate_sha256'],result['output_sha256'])

    def scenario(self,root,*,fail=False):
        from test_v2_workflow import V2WorkflowTests
        source,_,o=overlap_fixture(root);model=Path(root)/'fake.pt';model.write_bytes(b'fake weights')
        def transform(row,item):
            if row['decision']=='REMOVE_TEXT':row['watermarks']=copy.deepcopy(o['watermarks']);row['preserve_regions']=copy.deepcopy(o['preserve_regions'])
            return row
        with patch('mye_c_automation.image_repairs_v2.lama_torchscript',return_value=self.backend):
            return V2WorkflowTests().scenario(root,['REMOVE_TEXT','KEEP'],asset_images={0:source},observation_transform=transform,
                image_options={'lama_model_path':str(model)},quality_fail=fail)

    def test_normal_program_passes_actual_review_before_fake_upload_save(self):
        with tempfile.TemporaryDirectory() as d:
            result=self.scenario(Path(d))
            self.assertEqual(result['writer'].uploads,1);self.assertEqual(result['writer'].saves,1)
            q=json.loads((result['root']/'v2_quality.json').read_text())['items'][0]
            self.assertEqual(q['protection_review_status'],'PASS');self.assertTrue(result['result']['content_validation']['ok'])
            plan=json.loads((result['root']/'plan.v2.json').read_text())
            comparison=Path(q['protection_comparison_path']).relative_to(result['root']).as_posix()
            self.assertIn(comparison,[r['path'].replace('\\','/') for r in plan['evidence_refs']])

    def test_actual_damage_or_unknown_review_does_not_publish(self):
        with tempfile.TemporaryDirectory() as d:
            result=self.scenario(Path(d),fail='identity')
            self.assertIn('image_quality_v2',result['calls']);self.assertEqual(result['writer'].uploads,0)
            self.assertEqual(result['product']['images']['main'],result['original']['images']['main'])

    def test_unknown_quality_result_does_not_publish_a_trial(self):
        from mye_c_automation.ai_judge.client import JudgeClient
        classify=JudgeClient.classify;reviews=[]
        def unknown(client,task,*a,**kw):
            if task!='image_quality_v2':return classify(client,task,*a,**kw)
            reviews.append(True);return dict(status='NEEDS_REVIEW',results=[{}],models=['deepseek-v4.1-flash'])
        with tempfile.TemporaryDirectory() as d,patch.object(JudgeClient,'classify',unknown):
            result=self.scenario(Path(d));self.assertEqual(len(reviews),1);self.assertEqual(result['writer'].uploads,0)
            self.assertEqual(result['product']['images']['main'],result['original']['images']['main'])

    def test_one_residual_supplement_uses_original_and_stops_after_second_review(self):
        from mye_c_automation.ai_judge.client import JudgeClient
        from test_v2_workflow import V2WorkflowTests
        classify=JudgeClient.classify
        for stays in [False,True]:
            with self.subTest(stays=stays),tempfile.TemporaryDirectory() as d:
                root=Path(d);source,image,o=overlap_fixture(root);image[195:205,270:290]=(200,0,0);Image.fromarray(image).save(source)
                model=root/'fake.pt';model.write_bytes(b'fake');inputs=[];reviews=[]
                def backend(pixels,mask):inputs.append(pixels.copy());return self.backend(pixels,mask)
                def transform(row,item):
                    if row['decision']=='REMOVE_TEXT':row['watermarks']=copy.deepcopy(o['watermarks']);row['preserve_regions']=copy.deepcopy(o['preserve_regions'])
                    return row
                def wrapped(client,task,item,context,**kw):
                    if task!='image_quality_v2':return classify(client,task,item,context,**kw)
                    reviews.append(True);transport=client.transport
                    def response(model,evidence,ctx):
                        flags={k:True for k in ['identity_preserved','packaging_preserved','protected_print_preserved','overlay_removed','no_new_artifacts']}
                        row=dict(task_type=task,item_id=evidence['id'],confidence=.1,abstain=False,decision='MATCH',evidence_ids=evidence['evidence_ids'],checks=flags)
                        if len(reviews)==1 or stays:
                            flags['overlay_removed']=False;row['decision']='MISMATCH';row['residual_watermarks']=[dict(kind='STORE_WATERMARK',action='REMOVE_TEXT',
                                bbox=[.82,.79,.94,.89],confidence=.1,preserve_overlap_risk='LOW',repair_mode='REGION')]
                        return dict(choices=[dict(message=dict(content=json.dumps(row)))],usage=dict(prompt_tokens=1,completion_tokens=1,total_tokens=2))
                    client.transport=response
                    try:return classify(client,task,item,context,**kw)
                    finally:client.transport=transport
                with patch.object(JudgeClient,'classify',wrapped),patch('mye_c_automation.image_repairs_v2.lama_torchscript',return_value=backend):
                    result=V2WorkflowTests().scenario(root,['REMOVE_TEXT','KEEP'],asset_images={0:source},observation_transform=transform,image_options={'lama_model_path':str(model)})
                self.assertEqual(len(reviews),2);self.assertEqual(len(inputs),2)
                self.assertTrue(np.array_equal(inputs[0],inputs[1]));self.assertEqual(result['writer'].uploads,0 if stays else 1)

    def test_actual_print_damage_is_not_a_passing_review(self):
        from mye_c_automation.ai_judge.client import JudgeClient
        classify=JudgeClient.classify
        def wrapped(client,task,item,context,**kw):
            if task!='image_quality_v2':return classify(client,task,item,context,**kw)
            transport=client.transport
            def response(model,evidence,ctx):
                flags={k:True for k in ['identity_preserved','packaging_preserved','protected_print_preserved','overlay_removed','no_new_artifacts']};flags['protected_print_preserved']=False
                row=dict(task_type=task,item_id=evidence['id'],confidence=.99,abstain=False,decision='MISMATCH',evidence_ids=evidence['evidence_ids'],checks=flags)
                return dict(choices=[dict(message=dict(content=json.dumps(row)))],usage=dict(prompt_tokens=1,completion_tokens=1,total_tokens=2))
            client.transport=response
            try:return classify(client,task,item,context,**kw)
            finally:client.transport=transport
        with tempfile.TemporaryDirectory() as d,patch.object(JudgeClient,'classify',wrapped):
            result=self.scenario(Path(d));self.assertEqual(result['writer'].uploads,0)
            q=json.loads((result['root']/'v2_quality.json').read_text())['items'][0]
            self.assertEqual(q['quality_status'],'FAIL_IDENTITY');self.assertEqual(q['protection_review_status'],'NOT_PASSED')

    def test_tampered_protected_comparison_cannot_be_approved_again(self):
        from mye_c_automation.v2_remediation import verify
        with tempfile.TemporaryDirectory() as d:
            result=self.scenario(Path(d));root=result['root']
            row=next(r for r in json.loads((root/'v2_action_proofs.json').read_text())['candidates'] if r['action']=='REMOVE_TEXT')
            q=json.loads((root/'v2_quality.json').read_text());q['items'][0]['protected_region_comparison']['changed_pixels']=0
            (root/'v2_quality.json').write_text(json.dumps(q))
            with self.assertRaisesRegex(ValueError,'PROTECTION_COMPARISON'):verify(root,row,result['original'])
