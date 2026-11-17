import copy,hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
from test_global_watermark_flow import global_observation

def fixture(root):
    image,o,_=global_observation();source=root/'source.png';Image.fromarray(image).save(source)
    o['image_sha256']=hashlib.sha256(source.read_bytes()).hexdigest()
    box=o['watermarks'][0]['glyph_template_bbox'];w,h=Image.open(source).size
    regions=[dict(id='T1',polygon=[[box[0]*w,box[1]*h],[box[2]*w,box[1]*h],[box[2]*w,box[3]*h],[box[0]*w,box[3]*h]],observations=[dict(text='STORE',score=.01)])]
    selection=dict(remove_groups=[dict(text='STORE',ids=['T1'])],keep_ids=[],uncertain_ids=[],missed_texts=[])
    return source,o,regions,selection

class OcrFallbackTests(unittest.TestCase):
    def test_invalid_or_duplicated_ids_rejected(self):
        from mye_c_automation.watermark_processing.ocr_fallback import validate_selection
        with tempfile.TemporaryDirectory() as d:
            _,o,regions,selection=fixture(Path(d))
            for ids in [['T9'],['T1','T1'],[]]:
                value=copy.deepcopy(selection);value['remove_groups'][0]['ids']=ids
                with self.assertRaises(ValueError):validate_selection(value,regions,o)

    def test_named_protected_text_selection_rejected_but_overlap_allowed(self):
        from mye_c_automation.watermark_processing.ocr_fallback import validate_selection
        with tempfile.TemporaryDirectory() as d:
            _,o,r,s=fixture(Path(d));o['preserve_regions']=[dict(kind='JEZZY product title',bbox=[0,0,1,1],scope='EXACT_REGION')]
            self.assertEqual(validate_selection(s,r,o),s)
            s['remove_groups'][0]['text']='JEZZY'
            with self.assertRaisesRegex(ValueError,'PROTECTED_TEXT_CONFLICT'):validate_selection(s,r,o)

    def test_empty_selection_and_uncertain_selection_cannot_produce_mask(self):
        from mye_c_automation.watermark_processing.ocr_fallback import validate_selection
        with tempfile.TemporaryDirectory() as d:
            _,o,r,s=fixture(Path(d));s.update(remove_groups=[],uncertain_ids=['T1'])
            with self.assertRaisesRegex(ValueError,'SELECTION_UNRESOLVED'):validate_selection(s,r,o)

    def test_policy_enabled_by_default_and_explicit_false_supported(self):
        from mye_c_automation.watermark_processing.contracts import policy_options
        self.assertTrue(policy_options()['ocr_fallback']);self.assertFalse(policy_options({'ocr_fallback':False})['ocr_fallback'])

    def test_integrity_failure_is_not_eligible_for_ocr_retry(self):
        from mye_c_automation.watermark_processing.ocr_fallback import eligible_failure
        for reason in ['RIGHTS_NOT_AUTHORIZED','ORIGINAL_CHANGED','SOURCE_UNVERIFIED','INVALID_BBOX','FACTORY_TEXT_REMOVE_CONFLICT']:
            self.assertFalse(eligible_failure(reason))
        self.assertTrue(eligible_failure('GLYPH_TEMPLATE_BACKGROUND'))

    def test_no_detections_never_calls_model(self):
        from mye_c_automation.watermark_processing.ocr_fallback import prepare_fallback
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source,o,_,_=fixture(root)
            with patch('mye_c_automation.watermark_processing.ocr_fallback.extract_regions',return_value=dict(regions=[],passes=[])):
                with self.assertRaisesRegex(ValueError,'EMPTY_DETECTION'):prepare_fallback(source,o,root/'fallback',None,{})

    def test_selection_uses_existing_ledger_and_does_not_leak_description(self):
        from mye_c_automation.ai_judge.client import JudgeClient
        from mye_c_automation.budget_manager import BudgetManager
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source,o,r,s=fixture(root);budget=BudgetManager({'ai_requests':1,'full_resolution_images':2},root/'budget.sqlite')
            budget.configure_model_budget({'mode':'RECORD_ONLY','usage_source':'FAKE_TRANSPORT'},'OCR_TEST');seen=[]
            def transport(model,item,context):
                seen.append((model,item,context));self.assertNotIn('secret-description',json.dumps((item,context)))
                return dict(choices=[dict(message=dict(content=json.dumps(s)),finish_reason='stop')],usage=dict(prompt_tokens=2,completion_tokens=3,total_tokens=5))
            try:
                client=JudgeClient(budget,root/'cache',transport=transport,retries=0)
                raw=client.select_ocr_regions(source,source,r,o,{'pid':1,'descriptionJson':'secret-description'})
                self.assertEqual(len(seen),1);self.assertEqual(client.metrics['requests'],1)
                self.assertEqual(client.metrics['total_tokens'],5);self.assertEqual(budget.model_snapshot()['known_tokens'],5)
                self.assertEqual(json.loads(raw['choices'][0]['message']['content']),s)
            finally:budget.close()

    def test_glyph_plan_keeps_original_protection_and_binds_evidence(self):
        from mye_c_automation.watermark_processing.ocr_fallback import prepare_fallback,verify_fallback
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source,o,r,s=fixture(root);before=copy.deepcopy(o)
            class Judge:
                def select_ocr_regions(self,*a,**k):return dict(choices=[dict(finish_reason='stop',message=dict(content=json.dumps(s)))])
            with patch('mye_c_automation.watermark_processing.ocr_fallback.extract_regions',return_value=dict(regions=r,passes=[])):
                derived,ref=prepare_fallback(source,o,root/'fallback',Judge(),{})
            self.assertEqual(o,before);self.assertEqual(derived['preserve_regions'],o['preserve_regions'])
            self.assertTrue(all(m['repair_mode']=='TEMPLATE_GLYPHS' for m in derived['watermarks']))
            repair=dict(ocr_fallback=ref,execution_observation=derived)
            verify_fallback(root,repair,source,o)
            manifest=Path(ref['path']);data=json.loads(manifest.read_text());target=manifest.parent/data['files'][0]['path'];target.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'OCR_FALLBACK'):verify_fallback(root,repair,source,o)

    def scenario(self,root,*,primary_error=False,second_bad=False,disable=False,rights='OWNED_OR_LICENSED',first_pass=False):
        from test_v2_workflow import V2WorkflowTests
        from mye_c_automation.ai_judge.client import JudgeClient
        import mye_c_automation.image_repairs_v2 as repairs
        source,o,r,s=fixture(root);model=root/'fake.pt';model.write_bytes(b'fake')
        inputs=[];reviews=[];selections=[];actual_remove=repairs.remove_text
        def backend(pixels,mask):inputs.append(pixels.copy());pixels[mask>0]=0;return pixels
        def transform(row,item):
            if row['decision']=='REMOVE_TEXT':row['watermarks']=copy.deepcopy(o['watermarks']);row['preserve_regions']=copy.deepcopy(o['preserve_regions'])
            return row
        classify=JudgeClient.classify
        def review(client,task,item,context,**kw):
            if task!='image_quality_v2':return classify(client,task,item,context,**kw)
            reviews.append(1);old=client.transport
            def respond(model,evidence,ctx):
                checks={k:True for k in ['identity_preserved','packaging_preserved','protected_print_preserved','overlay_removed','no_new_artifacts']}
                bad=(not first_pass and len(reviews)==1 and not primary_error) or second_bad
                if bad:checks['identity_preserved']=False
                return dict(choices=[dict(message=dict(content=json.dumps(dict(task_type=task,item_id=evidence['id'],decision='MISMATCH' if bad else 'MATCH',abstain=False,confidence=.1,evidence_ids=evidence['evidence_ids'],checks=checks))))],usage=dict(prompt_tokens=1,completion_tokens=1,total_tokens=2))
            client.transport=respond
            try:return classify(client,task,item,context,**kw)
            finally:client.transport=old
        def select(client,*args,**kwargs):
            selections.append(1);return dict(choices=[dict(finish_reason='stop',message=dict(content=json.dumps(s)))])
        def remove(*a,**kw):
            if primary_error and not selections:raise ValueError('GLYPH_TEMPLATE_BACKGROUND')
            return actual_remove(*a,**kw)
        with patch('mye_c_automation.watermark_processing.ocr_fallback.extract_regions',return_value=dict(regions=r,passes=[])),patch.object(JudgeClient,'select_ocr_regions',select),patch.object(JudgeClient,'classify',review),patch.object(repairs,'remove_text',side_effect=remove),patch.object(repairs,'lama_torchscript',return_value=backend):
            result=V2WorkflowTests().scenario(root,['REMOVE_TEXT','KEEP'],rights=rights,asset_images={0:source},observation_transform=transform,
                image_options={'lama_model_path':str(model),'watermark_processing':{'ocr_fallback':not disable}})
        return result,inputs,reviews,selections

    def test_failed_quality_uses_original_ocr_and_independent_readback(self):
        with tempfile.TemporaryDirectory() as d:
            result,inputs,reviews,selections=self.scenario(Path(d))
            self.assertEqual((len(inputs),len(reviews),len(selections)),(2,2,1))
            self.assertTrue(np.array_equal(inputs[0],inputs[1]));self.assertEqual(result['writer'].uploads,1)
            self.assertTrue(result['result']['content_validation']['ok'])
            plan=json.loads((result['root']/'plan.v2.json').read_text())
            self.assertTrue(any('ocr-fallback' in r['path'] for r in plan['evidence_refs']))

    def test_mask_failure_uses_single_ocr_attempt(self):
        with tempfile.TemporaryDirectory() as d:
            result,inputs,reviews,selections=self.scenario(Path(d),primary_error=True)
            self.assertEqual((len(inputs),len(reviews),len(selections)),(1,1,1));self.assertEqual(result['writer'].uploads,1)

    def test_second_failure_stops_without_third_candidate(self):
        with tempfile.TemporaryDirectory() as d:
            result,inputs,reviews,selections=self.scenario(Path(d),second_bad=True)
            self.assertEqual((len(inputs),len(reviews),len(selections)),(2,2,1));self.assertEqual(result['writer'].uploads,0)

    def test_primary_success_never_runs_ocr(self):
        with tempfile.TemporaryDirectory() as d:
            result,inputs,reviews,selections=self.scenario(Path(d),first_pass=True)
            self.assertEqual((len(inputs),len(reviews),len(selections)),(1,1,0));self.assertEqual(result['writer'].uploads,1)

    def test_explicit_opt_out_keeps_identity_rejection(self):
        with tempfile.TemporaryDirectory() as d:
            result,inputs,reviews,selections=self.scenario(Path(d),disable=True)
            self.assertEqual((len(inputs),len(reviews),len(selections)),(1,1,0));self.assertEqual(result['writer'].uploads,0)

    def test_rights_failure_never_calls_ocr_or_backend(self):
        with tempfile.TemporaryDirectory() as d:
            result,inputs,reviews,selections=self.scenario(Path(d),rights='RIGHTS_UNKNOWN')
            self.assertEqual((len(inputs),len(reviews),len(selections)),(0,0,0));self.assertEqual(result['writer'].uploads,0)

if __name__=='__main__':unittest.main()
