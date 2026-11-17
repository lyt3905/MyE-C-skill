import copy,hashlib,json,tempfile,unittest
from pathlib import Path
from PIL import Image
from unittest.mock import patch

def initial(action='KEEP',box=False):
    return dict(decision=action,visual_class='RETAIL_BOX_ONLY' if box else 'TOY_PRODUCT',retail_box_status='PRESENT' if box else 'ABSENT',
        sku_suitability=dict(is_toy_photo=not box,is_retail_box_photo=box,recommended_group='WITH_RETAIL_BOX' if box else 'WITHOUT_RETAIL_BOX'),abstain=False,reason='Visible source evidence')

class StagedVisionTests(unittest.TestCase):
    def scenario(self,root,*,quality_bad=False,planning_bad=False,all_keep=False,ocr=False):
        from test_v2_workflow import V2WorkflowTests
        from test_template_glyph_repair import fixture
        from mye_c_automation.ai_judge.client import JudgeClient
        image,old,_=fixture();source=root/'source.png';Image.fromarray(image).save(source);digest=hashlib.sha256(source.read_bytes()).hexdigest()
        model=root/'fake.pt';model.write_bytes(b'fake');events=[];constructor=JudgeClient.__init__
        def init(client,*args,**kw):
            transport=kw.get('transport')
            if transport:
                def staged(model,item,context):
                    task=item['task_type'];events.append(task)
                    if task=='vision_initial':value=initial('KEEP' if all_keep or item['sha256']!=digest else 'REMOVE_TEXT')
                    elif task=='vision_planning':
                        marks=[dict(watermark_id='w'+str(i),group_id='g',action='REMOVE_TEXT',kind='STORE_WATERMARK',owner='THIRD_PARTY_STORE',content_type='TEXT',bbox=m['bbox']) for i,m in enumerate(old['watermarks'])]
                        value=dict(watermarks=marks,preserve_regions=[],reason='Added store text')
                        if planning_bad:value['watermarks'][0]['owner']='PRODUCT'
                    elif task=='vision_quality':
                        checks={k:True for k in ['identity_preserved','packaging_preserved','protected_print_preserved','overlay_removed','no_new_artifacts']}
                        bad=quality_bad and (quality_bad!='once' or events.count('vision_quality')==1)
                        if bad:checks['identity_preserved']=False
                        value=dict(decision='MISMATCH' if bad else 'MATCH',abstain=False,checks=checks,residual_watermarks=[],reason='Actual candidate comparison')
                    elif task=='ocr_watermark_selection':value=dict(remove_groups=[dict(text='GCC',ids=['T1'])],keep_ids=[],uncertain_ids=[],missed_texts=[])
                    else:return transport(model,item,context)
                    return dict(choices=[dict(finish_reason='stop',message=dict(content=json.dumps(value)))],usage=dict(prompt_tokens=2,completion_tokens=3,total_tokens=5))
                kw['transport']=staged
            constructor(client,*args,**kw);client.vision_protocol='staged-v1'
        def backend(pixels,mask):pixels[mask>0]=0;return pixels
        box=old['watermarks'][0]['glyph_template_bbox'];w,h=Image.open(source).size
        region=dict(id='T1',polygon=[[box[0]*w,box[1]*h],[box[2]*w,box[1]*h],[box[2]*w,box[3]*h],[box[0]*w,box[3]*h]],observations=[dict(text='GCC',score=.3)])
        with patch.object(JudgeClient,'__init__',init),patch('mye_c_automation.image_repairs_v2.lama_torchscript',return_value=backend),patch('mye_c_automation.watermark_processing.ocr_fallback.extract_regions',return_value=dict(regions=[region],passes=[])):
            result=V2WorkflowTests().scenario(root,['KEEP' if all_keep else 'REMOVE_TEXT','KEEP'],asset_images={0:source},image_options={'lama_model_path':str(model),'watermark_processing':{'ocr_fallback':ocr}})
        return result,events

    def test_native_keep_has_only_initial_requests(self):
        with tempfile.TemporaryDirectory() as d:
            result,calls=self.scenario(Path(d),all_keep=True)
            self.assertEqual(calls,['vision_initial','vision_initial']);self.assertEqual(result['writer'].uploads,0)

    def test_native_repair_conditionally_plans_and_reviews_then_reads_back(self):
        with tempfile.TemporaryDirectory() as d:
            result,calls=self.scenario(Path(d))
            self.assertEqual(calls,['vision_initial','vision_initial','vision_planning','vision_quality'])
            self.assertEqual(result['writer'].uploads,1);self.assertEqual(result['writer'].saves,1)
            self.assertTrue(result['result']['content_validation']['ok'])
            originals=json.loads((result['root']/'full_ai_judgements.json').read_text())
            o=next(v['observation'] for v in originals.values() if v['decision']=='REMOVE_TEXT')
            self.assertNotIn('watermarks',o);self.assertNotIn('confidence',o)
            self.assertTrue(list((result['root']/'v2_candidates').glob('*/planning/binding.json')))

    def test_native_planning_business_conflict_does_not_repair(self):
        with tempfile.TemporaryDirectory() as d:
            result,calls=self.scenario(Path(d),planning_bad=True)
            self.assertEqual(calls.count('vision_planning'),1);self.assertNotIn('vision_quality',calls);self.assertEqual(result['writer'].uploads,0)

    def test_native_second_quality_failure_never_uploads(self):
        with tempfile.TemporaryDirectory() as d:
            result,calls=self.scenario(Path(d),quality_bad=True)
            self.assertEqual(result['writer'].uploads,0);self.assertEqual(calls.count('vision_quality'),1)

    def test_staged_ocr_fallback_shares_two_candidates_and_has_no_fabricated_scores(self):
        with tempfile.TemporaryDirectory() as d:
            result,calls=self.scenario(Path(d),quality_bad='once',ocr=True)
            self.assertEqual(calls.count('ocr_watermark_selection'),1);self.assertEqual(calls.count('vision_quality'),2)
            self.assertEqual(result['writer'].uploads,1)
            quality=json.loads((result['root']/'v2_quality.json').read_text())['items']
            self.assertEqual(len(quality),2)
            for q in quality:
                self.assertNotIn('confidence',q['repair']['execution_observation'])
                for mark in q['repair']['execution_observation']['watermarks']:self.assertNotIn('confidence',mark)

    def test_modified_planning_evidence_cannot_reapprove_asset(self):
        from mye_c_automation.v2_remediation import verify
        with tempfile.TemporaryDirectory() as d:
            result,_=self.scenario(Path(d))
            proofs=json.loads((result['root']/'v2_action_proofs.json').read_text())['candidates'];row=next(p for p in proofs if p['action']=='REMOVE_TEXT')
            file=next((result['root']/'v2_candidates').glob('*/planning/response.json'));file.write_text('{}')
            with self.assertRaisesRegex(ValueError,'STAGED_PLAN'):verify(result['root'],row,result['original'])

    def test_explicit_legacy_config_and_configured_default(self):
        from mye_c_automation.ai_judge.client import JudgeClient
        from mye_c_automation.model_config import load_config
        from mye_c_automation.budget_manager import BudgetManager
        import mye_c_automation
        package=Path(mye_c_automation.__file__).resolve().parent
        config=load_config(package/'config/model.gateway8788.example.json')
        with tempfile.TemporaryDirectory() as d:
            budget=BudgetManager({'ai_requests':2,'full_resolution_images':2})
            try:
                self.assertEqual(JudgeClient(budget,Path(d)/'new',config=config).vision_protocol,'staged-v1')
                self.assertEqual(JudgeClient(budget,Path(d)/'old',config=dict(config,vision_protocol='legacy-v2')).vision_protocol,'legacy-v2')
            finally:budget.close()

    def test_initial_six_fields_and_no_legacy_score_padding(self):
        from mye_c_automation.ai_judge.staged_vision import bind_initial,validate_phase
        row=initial();validate_phase('initial',row)
        out=bind_initial(row,dict(id='x',sha256='a'*64,image_type='MAIN',evidence_ids=['SOURCE']))
        for name in ['confidence','toy_present','angle','clear','product_identity','box_relation','retail_box_bbox']:self.assertNotIn(name,out)
        self.assertEqual(out['image_sha256'],'a'*64);self.assertEqual(row,initial())

    def test_missing_extra_enum_and_wrong_type_rejected(self):
        from mye_c_automation.ai_judge.staged_vision import validate_phase
        values=[dict(initial(),confidence=.9),dict(initial(),decision='ERASE'),dict(initial(),abstain='false')]
        value=initial();value.pop('reason');values.append(value)
        for row in values:
            with self.assertRaises(ValueError):validate_phase('initial',row)

    def test_planning_cannot_remove_product_print_or_use_invalid_coordinates(self):
        from mye_c_automation.ai_judge.staged_vision import validate_phase
        mark=dict(watermark_id='w',group_id='g',action='REMOVE_TEXT',kind='PRODUCT_PRINT',owner='PRODUCT',content_type='TEXT',bbox=[.1,.1,.3,.3])
        for change in [{},{'kind':'STORE_WATERMARK','owner':'THIRD_PARTY_STORE','bbox':[.1,.1,1.1,.3]}]:
            with self.assertRaises(ValueError):validate_phase('planning',dict(watermarks=[dict(mark,**change)],preserve_regions=[],reason='target'))

    def test_quality_requires_five_checks_and_consistent_decision(self):
        from mye_c_automation.ai_judge.staged_vision import validate_phase
        checks={k:True for k in ['identity_preserved','packaging_preserved','protected_print_preserved','overlay_removed','no_new_artifacts']}
        row=dict(decision='MATCH',abstain=False,checks=checks,residual_watermarks=[],reason='Actual result preserved')
        validate_phase('quality',row)
        for key in checks:
            value=copy.deepcopy(row);value['checks'][key]=False
            with self.assertRaises(ValueError):validate_phase('quality',value)

    def test_first_prompt_is_under_six_thousand_characters(self):
        from mye_c_automation.ai_judge.staged_vision import phase_prompt
        self.assertLess(len(phase_prompt('initial')),6000)
        self.assertNotIn('glyph_template',phase_prompt('initial'))
        self.assertNotIn('confidence',phase_prompt('initial'))

    def test_staged_request_uses_same_ledger_and_never_legacy_fallback(self):
        from mye_c_automation.ai_judge.client import JudgeClient
        from mye_c_automation.budget_manager import BudgetManager
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);path=root/'source.png';Image.new('RGB',(80,80),'white').save(path)
            budget=BudgetManager({'ai_requests':4,'full_resolution_images':8},root/'budget.sqlite');budget.configure_model_budget({'mode':'RECORD_ONLY','usage_source':'FAKE_TRANSPORT'},'staged')
            calls=[]
            def transport(model,item,context):
                calls.append(item['task_type']);return dict(choices=[dict(finish_reason='stop',message=dict(content=json.dumps(initial())))],usage=dict(prompt_tokens=2,completion_tokens=3,total_tokens=5))
            try:
                client=JudgeClient(budget,root/'cache',transport=transport,retries=0)
                item=dict(id='i',sha256=hashlib.sha256(path.read_bytes()).hexdigest(),local=str(path),image_type='MAIN',evidence_ids=['SOURCE'])
                value=client.request_vision_phase('initial',item,{})
                self.assertEqual(value['result'],initial());self.assertEqual(calls,['vision_initial'])
                self.assertEqual(budget.model_snapshot()['known_tokens'],5)
                client.request_vision_phase('initial',item,{})
                self.assertEqual(len(calls),1)
            finally:budget.close()

if __name__=='__main__':unittest.main()
