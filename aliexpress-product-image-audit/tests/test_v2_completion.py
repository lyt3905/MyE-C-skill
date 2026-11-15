import json
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_v2_vision import observation
import test_v2_workflow as fixtures


class V2CompletionTests(unittest.TestCase):
    def test_full_audit_cli_defaults_to_v2_without_ocr_template_requirement(self):
        import workflow_runner
        from job_manager import atomic_json
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);atomic_json(root/'site.json',{})
            profile=json.loads(Path('scripts/config/model.gateway8788.example.json').read_text(encoding='utf-8'))
            atomic_json(root/'model.json',profile)
            argv=['workflow_runner.py','full-audit','--pid','1','--shop','7','--site-config',str(root/'site.json'),'--model-config',str(root/'model.json'),'--root',str(root/'jobs')]
            with patch('sys.argv',argv),patch('site_client.ReadOnlySiteClient'),patch('full_product_audit.run_full_audit',return_value={'job_id':'FAKE_ONLY'}) as audit:
                workflow_runner.main()
            self.assertEqual(audit.call_args.kwargs['image_workflow'],'v2')
            self.assertIsNone(audit.call_args.kwargs['template_config'])

    def test_standalone_v2_audit_freezes_new_job_and_uses_unified_strategy(self):
        from full_product_audit import run_full_audit
        class Reader:
            def current_shop(self):return 7
            def account_fingerprint(self):return 'b'*64
        with tempfile.TemporaryDirectory() as directory,patch('full_product_audit.run_unified_audit',return_value={'fake':True}) as unified:
            result=run_full_audit(directory,1,7,Reader(),image_workflow='v2',model_budget={'mode':'RECORD_ONLY','usage_source':'FAKE_TRANSPORT'})
            manager,job,reader=unified.call_args.args
            self.assertEqual(job['image_workflow'],'v2');self.assertEqual(job,manager.load(job['job_id']))
            self.assertFalse(job['templates_required']);self.assertTrue(result['fake'])
            unified.reset_mock()
            run_full_audit(directory,1,7,Reader(),job=job)
            self.assertIsNotNone(unified.call_args.args[0])

    def test_missing_sku_id_preserves_reference_while_independent_main_repair_continues(self):
        with tempfile.TemporaryDirectory() as directory:
            scenario=fixtures.V2WorkflowTests().scenario(directory,['REMOVE_TEXT','KEEP'],sku_on_first=True,missing_sku_id=True)
            self.assertEqual(scenario['writer'].saves,1);self.assertEqual(scenario['writer'].uploads,1)
            self.assertEqual(scenario['product']['images']['main'][0],'https://fake/upload1')
            self.assertEqual(scenario['product']['skus'][0]['skuImageUrl'],'https://fake/0')
            self.assertEqual(scenario['product']['images']['sku'],scenario['original']['images']['sku'])
            self.assertTrue(scenario['result']['content_validation']['ok'])
            self.assertEqual(scenario['result']['status'],'PARTIALLY_AUTO_FIXED')

    def test_delete_sku_reassignment_to_repaired_image_resolves_both_operations(self):
        with tempfile.TemporaryDirectory() as directory:
            scenario=fixtures.V2WorkflowTests().scenario(directory,['DELETE','REMOVE_TEXT'],sku_on_first=True)
            self.assertEqual(scenario['writer'].saves,1);self.assertEqual(scenario['writer'].uploads,1)
            self.assertEqual(scenario['product']['images']['main'],['https://fake/upload1'])
            self.assertEqual(scenario['product']['skus'][0]['skuImageUrl'],'https://fake/upload1')
            self.assertTrue(scenario['result']['content_validation']['ok'])

    def test_reference_only_delete_is_resolved_by_authorized_existing_sku_assignment(self):
        with tempfile.TemporaryDirectory() as directory:
            scenario=fixtures.V2WorkflowTests().scenario(directory,['DELETE','KEEP'],reference_only=True)
            self.assertEqual(scenario['writer'].saves,1)
            self.assertEqual(scenario['product']['skus'][0]['skuImageUrl'],'https://fake/1')
            deferred=json.loads((scenario['root']/'deferred_items.json').read_text())['items']
            self.assertFalse(any(r.get('target',{}).get('sku_row_index')==0 for r in deferred))
            decisions=json.loads((scenario['root']/'auto_decisions.json').read_text())['items']
            self.assertTrue(any(r['source'].get('reference_deletions') for r in decisions if r.get('decision')=='AUTO_SAFE'))
            plan=json.loads((scenario['root']/'plan.v2.json').read_text())
            self.assertIn('DELETE',plan['automation']['actions'])

    def retained_box_scenario(self,directory,corrupt=None):
        def boxes(item,decision='KEEP',**changes):
            result=observation(item,decision,**changes)
            result.update(visual_class='TOY_WITH_RETAIL_BOX',retail_box_status='PRESENT',retail_box_bbox=[.1,.1,.3,.4],box_relation='SAME_PRODUCT')
            result['sku_suitability']['is_retail_box_photo']=True
            return result
        with patch('test_v2_workflow.observation',side_effect=boxes):
            return fixtures.V2WorkflowTests().scenario(directory,['DELETE','KEEP'],corrupt_readback=corrupt)

    def test_box_composite_deletion_can_continue_when_packaging_evidence_remains(self):
        with tempfile.TemporaryDirectory() as directory:
            scenario=self.retained_box_scenario(directory)
            self.assertEqual(scenario['writer'].saves,1)
            self.assertEqual(scenario['product']['images']['main'],['https://fake/1'])
            self.assertTrue(scenario['result']['content_validation']['ok'])
            decisions=json.loads((scenario['root']/'auto_decisions.json').read_text())['items']
            self.assertTrue(any(row['source'].get('retained_references') for row in decisions if row.get('decision')=='AUTO_SAFE'))

    def test_retained_box_byte_drift_fails_content_verification_without_resave(self):
        with tempfile.TemporaryDirectory() as directory:
            scenario=self.retained_box_scenario(directory,corrupt='retained_bytes')
            self.assertEqual(scenario['writer'].saves,1)
            self.assertFalse(scenario['result']['content_validation']['ok'])
            self.assertEqual(scenario['result']['status'],'REVIEW_REQUIRED')
            observed=[value for item in scenario['result']['content_validation']['items'] for value in item['readback']]
            self.assertTrue(any(value['observed_sha256']!=value['expected_sha256'] for value in observed))

    def test_deleted_image_sku_reference_is_reassigned_in_same_single_save(self):
        with tempfile.TemporaryDirectory() as directory:
            scenario=fixtures.V2WorkflowTests().scenario(directory,['DELETE','KEEP'],sku_on_first=True)
            self.assertEqual(scenario['writer'].saves,1)
            self.assertEqual(scenario['writer'].uploads,0)
            self.assertEqual(scenario['product']['skus'][0]['skuImageUrl'],'https://fake/1')
            for pool in ('main','detail','sku'):self.assertNotIn('https://fake/0',scenario['product']['images'][pool])
            self.assertTrue(scenario['result']['content_validation']['ok'])

    def test_deletion_preserves_last_retail_box_evidence(self):
        def boxes(item,decision='KEEP',**changes):
            result=observation(item,decision,**changes)
            if decision=='DELETE':
                result.update(visual_class='TOY_WITH_RETAIL_BOX',retail_box_status='PRESENT',retail_box_bbox=[.1,.1,.3,.4],box_relation='SAME_PRODUCT')
                result['sku_suitability']['is_retail_box_photo']=True
            return result
        with tempfile.TemporaryDirectory() as directory,patch('test_v2_workflow.observation',side_effect=boxes):
            scenario=fixtures.V2WorkflowTests().scenario(directory,['DELETE','KEEP'])
            self.assertIn('https://fake/0',scenario['product']['images']['main'])
            deferred=json.loads((scenario['root']/'deferred_items.json').read_text())['items']
            self.assertTrue(any('LAST_RETAIL_BOX_EVIDENCE' in row.get('reason_codes',[]) for row in deferred))

    def test_v2_cross_job_duplicate_plan_does_not_save_again(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);ledger=root/'shared-ledger.sqlite'
            first=fixtures.V2WorkflowTests().scenario(root,['DELETE','KEEP'],product_id=301,ledger_path=ledger)
            sealed=(first['root']/'full_audit_evidence_manifest.json').read_bytes()
            second=fixtures.V2WorkflowTests().scenario(root,['DELETE','KEEP'],product_id=301,ledger_path=ledger)
            self.assertNotEqual(first['root'],second['root'])
            self.assertEqual(first['writer'].saves,1)
            self.assertEqual(second['writer'].saves,0)
            self.assertEqual(second['result']['status'],'REVIEW_REQUIRED')
            self.assertEqual(second['result']['technical_status'],'DEFERRED')
            self.assertEqual(second['result']['reason'],'DUPLICATE_OPERATION')
            self.assertEqual((first['root']/'full_audit_evidence_manifest.json').read_bytes(),sealed)

    def test_possible_same_product_relation_is_record_only_and_uncertain_box_still_reviews(self):
        import test_v2_vision as vision
        helper=vision.VisionTests();helper.setUp()
        try:
            client,calls=helper.client(lambda m,i:observation(i,visual_class='TOY_WITH_RETAIL_BOX',retail_box_status='PRESENT',retail_box_bbox=[.1,.1,.3,.4],box_relation='POSSIBLY_SAME_PRODUCT'))
            result=helper.decide(client)
            self.assertEqual(result['decision'],'KEEP')
            self.assertEqual(result['results'][0]['box_relation'],'POSSIBLY_SAME_PRODUCT')
            self.assertEqual(len(calls),1)
            helper.item['purpose']='uncertain-packaging-control'
            client,calls=helper.client(lambda m,i:observation(i,retail_box_status='UNCERTAIN',box_relation='POSSIBLY_SAME_PRODUCT'))
            self.assertEqual(helper.decide(client)['decision'],'REVIEW')
            self.assertEqual(len(calls),1)
        finally:helper.doCleanups()

    def test_protected_and_unknown_text_keep_unchanged_with_v2_client(self):
        import test_v2_vision as vision
        for kind in ('MANUFACTURER_LOGO','PRODUCT_PRINT','PACKAGING_PRINT','CREATOR_CREDIT','UNKNOWN_TEXT'):
            with self.subTest(kind=kind):
                helper=vision.VisionTests();helper.setUp()
                try:
                    client,calls=helper.client(lambda m,i:observation(i,watermarks=[dict(kind=kind,bbox=[.1,.1,.2,.2],confidence=.95,preserve_overlap_risk='LOW')]))
                    result=helper.decide(client)
                    self.assertEqual(result['decision'],'KEEP')
                    self.assertEqual(result['observation']['watermarks'],[dict(kind=kind,bbox=[.1,.1,.2,.2],confidence=.95,preserve_overlap_risk='LOW')])
                    self.assertEqual([row['watermarks'] for row in result['results']],[result['observation']['watermarks']])
                    self.assertEqual(len(calls),1)
                finally:helper.doCleanups()

    def test_failed_regeneration_identity_never_uploads_or_repeats_edit(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as directory:
            scenario=fixtures.V2WorkflowTests().scenario(directory,['AI_REGENERATE','KEEP'],edit_backend=True,quality_fail='identity')
            self.assertEqual(scenario['writer'].uploads,0)
            self.assertEqual(scenario['writer'].saves,0)
            checks=json.loads((scenario['root']/'v2_quality.json').read_text())['items']
            self.assertEqual(len(checks),1);self.assertEqual(checks[0]['quality_status'],'FAIL_IDENTITY')
            db=sqlite3.connect(scenario['root']/'budget.sqlite')
            try:self.assertEqual(sum(json.loads(r[0])['task_type']=='image_edit_v2' for r in db.execute('SELECT metadata FROM model_calls')),1)
            finally:db.close()

    def test_local_repair_preserves_transparency_outside_mask(self):
        import numpy as np
        from PIL import Image,ImageDraw
        from image_repairs_v2 import remove_text,deterministic_quality
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'rgba.png';image=Image.new('RGBA',(800,800),(255,255,255,0))
            draw=ImageDraw.Draw(image);draw.rectangle((250,200,550,600),fill=(20,70,140,255));draw.text((20,740),'STORE',fill=(255,0,0,255));image.save(source)
            item={'id':'I','sha256':'a'*64,'image_type':'SKU','evidence_ids':['S']}
            obs=observation(item,'REMOVE_TEXT',watermarks=[dict(kind='STORE_WATERMARK',bbox=[.02,.92,.12,.95],confidence=.95,preserve_overlap_risk='LOW')])
            result=remove_text(source,obs,root/'out',rights='OWNED_OR_LICENSED')
            with Image.open(result['output_path']) as repaired:
                self.assertEqual(repaired.mode,'RGBA')
                self.assertEqual(repaired.getpixel((0,0))[3],0)
            self.assertTrue(deterministic_quality(source,result['output_path'],result['mask_path'])['ok'])
            broken=Image.open(result['output_path']).convert('RGB');broken.save(root/'lost-alpha.png')
            self.assertFalse(deterministic_quality(source,root/'lost-alpha.png',result['mask_path'])['ok'])

    def test_reference_only_sku_image_is_repaired_uploaded_and_bound_to_existing_id(self):
        with tempfile.TemporaryDirectory() as directory:
            scenario=fixtures.V2WorkflowTests().scenario(directory,['REMOVE_TEXT','KEEP'],reference_only=True)
            self.assertEqual(scenario['writer'].uploads,1)
            self.assertEqual(scenario['writer'].saves,1)
            self.assertEqual(scenario['product']['skus'][0]['skuId'],'real1')
            self.assertEqual(scenario['product']['skus'][0]['skuImageUrl'],'https://fake/upload1')
            self.assertIn('https://fake/upload1',scenario['product']['images']['sku'])
            self.assertTrue(scenario['result']['content_validation']['ok'])
            self.assertEqual(scenario['product']['images']['main'],scenario['original']['images']['main'])

    def test_reference_only_review_remains_explicitly_deferred(self):
        with tempfile.TemporaryDirectory() as directory:
            scenario=fixtures.V2WorkflowTests().scenario(directory,['REVIEW','KEEP'],reference_only=True)
            deferred=json.loads((scenario['root']/'deferred_items.json').read_text())['items']
            self.assertTrue(any(r.get('target',{}).get('sku_row_index')==0 for r in deferred))
            self.assertEqual(scenario['product']['skus'][0]['skuImageUrl'],'https://fake/0')
            self.assertEqual(scenario['writer'].uploads,0)

    def test_sku_selector_preserves_valid_existing_reference_and_respects_suitability(self):
        from sku_assignment import select_v2
        from test_v2_repairs_sku import RepairSkuTests
        records=RepairSkuTests().records()
        product={'skus':[{'id':'real','skuName':'Without Box','skuImageUrl':'https://fake/2'}]}
        result=select_v2(product,records)
        self.assertEqual(result['assignments'],{'real':'https://fake/2'})
        for row in records:row['observation']['sku_suitability']['is_toy_photo']=False
        self.assertFalse(select_v2(product,records)['selected_sku_images'])

    def test_two_no_box_candidates_both_enter_existing_sku_image_pool(self):
        def with_accessory(item,decision='KEEP',**changes):
            result=observation(item,decision,**changes)
            if decision=='KEEP':result['visual_class']='ACCESSORY';result['sku_suitability']['is_toy_photo']=False
            return result
        with tempfile.TemporaryDirectory() as directory,patch('test_v2_workflow.observation',side_effect=with_accessory):
            scenario=fixtures.V2WorkflowTests().scenario(directory,['REMOVE_TEXT','REMOVE_TEXT','KEEP'])
            selection=json.loads((scenario['root']/'v2_sku_selection.json').read_text())
            plan=json.loads((scenario['root']/'plan.v2.json').read_text())
            before=json.loads((scenario['root']/'audit_product.json').read_text())
            selected_urls=[r['url'] for r in selection['selected_sku_images']]
            self.assertEqual(len(selected_urls),2)
            for url in selected_urls:
                self.assertIn(url,plan['desired']['images']['sku'])
            self.assertEqual(scenario['writer'].uploads,2)
            self.assertTrue(scenario['result']['content_validation']['ok'])
            self.assertEqual(len(scenario['product']['skus']),len(before['skus']))

    def test_v2_one_three_ten_products_use_real_jobs_and_shared_fake_ledger(self):
        from batch_scheduler import run_batch
        from automation_policy import AutomationPolicy
        from test_auto_decision import CONFIG
        for count in (1,3,10):
            with self.subTest(count=count),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);completed=[];pids=list(range(101,101+count))
                config=copy.deepcopy(CONFIG);config['allow_actions'].update(DELETE=True,SKU_ASSIGN=True)
                def run_one(pid,shop):
                    scenario=fixtures.V2WorkflowTests().scenario(root/str(pid),['DELETE','KEEP'],product_id=pid,ledger_path=root/'batch-ledger.sqlite')
                    self.assertEqual(scenario['product']['id'],pid)
                    self.assertEqual(scenario['writer'].saves,1)
                    self.assertEqual(scenario['product']['descriptionJson'],scenario['original']['descriptionJson'])
                    self.assertEqual(scenario['product']['price'],scenario['original']['price'])
                    self.assertTrue(scenario['result']['content_validation']['ok'])
                    completed.append(scenario)
                    return scenario['result']
                result=run_batch(pids,7,AutomationPolicy(config),run_one)
                self.assertFalse(result['halted']);self.assertEqual(result['write_concurrency'],1)
                self.assertEqual([r['pid'] for r in result['items']],pids)
                self.assertEqual(len(completed),count)
                self.assertFalse(result['not_started'])

    def test_v2_batch_stops_after_unknown_save_without_creating_next_job(self):
        from batch_scheduler import run_batch
        from automation_policy import AutomationPolicy
        from test_auto_decision import CONFIG
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);started=[]
            def run_one(pid,shop):
                started.append(pid)
                return fixtures.V2WorkflowTests().scenario(root/str(pid),['DELETE','KEEP'],product_id=pid,save_timeout=True,ledger_path=root/'ledger.sqlite')['result']
            result=run_batch([201,202,203],7,AutomationPolicy(copy.deepcopy(CONFIG)),run_one)
            self.assertTrue(result['halted']);self.assertEqual(started,[201])
            self.assertEqual(result['not_started'],[202,203])
            self.assertFalse((root/'202').exists())

    def test_local_torchscript_adapter_accepts_installed_lama_two_tensor_contract(self):
        import numpy as np
        import torch
        from image_repairs_v2 import lama_torchscript
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'synthetic-contract-only.pt'
            graph=torch.jit.CompilationUnit('def forward(image: Tensor, mask: Tensor) -> Tensor:\n    return image * (1.0 - mask) + mask * 0.75\n')
            torch.jit.save(graph.forward,str(path))
            adapter=lama_torchscript(path)
            image=np.zeros((801,805,3),dtype=np.uint8);mask=np.zeros((801,805),dtype=np.uint8);mask[10:20,10:20]=255
            result=adapter(image,mask)
            self.assertEqual(result.shape,image.shape)
            self.assertGreater(int(result[12,12,0]),180)
            self.assertEqual(result[30,30,0],0)
            dictionary=torch.jit.CompilationUnit('def forward(data: Dict[str, Tensor]) -> Tensor:\n    return data["image"] * (1.0 - data["mask"]) + data["mask"] * 0.75\n')
            torch.jit.save(dictionary.forward,str(path))
            result_dict=lama_torchscript(path)(image,mask)
            self.assertTrue(np.array_equal(result,result_dict))

    def test_frozen_configured_edit_adapter_runs_through_normal_prepare_and_budget(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as directory:
            adapter=Path(directory)/'local_fake_edit.py'
            adapter.write_text('''from pathlib import Path
from PIL import Image,ImageDraw
def edit_image(source,context,observation,destination):
    assert "descriptionJson" not in context
    assert "_image_edit_constraints" in context
    image=Image.open(source).convert("RGB")
    ImageDraw.Draw(image).point((1,1),fill="gray")
    output=Path(destination)/"configured.png"
    image.save(output)
    return {"candidate_path":str(output),"usage":{"prompt_tokens":6,"completion_tokens":4,"total_tokens":10}}
''',encoding='utf-8')
            spec={'adapter_path':str(adapter),'model':'deepseek-v4.1-flash'}
            scenario=fixtures.V2WorkflowTests().scenario(directory,['AI_REGENERATE','KEEP'],image_options={'image_edit':spec})
            self.assertEqual(scenario['writer'].uploads,1)
            self.assertTrue(scenario['result']['content_validation']['ok'])
            frozen=json.loads((scenario['root']/'job.json').read_text())['image_options']['image_edit']
            self.assertEqual(len(frozen['adapter_sha256']),64)
            db=sqlite3.connect(scenario['root']/'budget.sqlite')
            try:
                events=[json.loads(r[0]) for r in db.execute('SELECT metadata FROM model_calls')]
                self.assertEqual(sum(r['task_type']=='image_edit_v2' for r in events),1)
            finally:db.close()

    def test_repaired_image_selected_for_sku_verifies_resolved_upload_url(self):
        def with_accessory(item,decision='KEEP',**changes):
            result=observation(item,decision,**changes)
            if decision=='KEEP':
                result['visual_class']='ACCESSORY'
                result['sku_suitability']['is_toy_photo']=False
            return result
        with tempfile.TemporaryDirectory() as directory,patch('test_v2_workflow.observation',side_effect=with_accessory):
            scenario=fixtures.V2WorkflowTests().scenario(directory,['REMOVE_TEXT','KEEP'])
            self.assertEqual(scenario['writer'].saves,1)
            self.assertEqual(scenario['writer'].uploads,1)
            self.assertEqual(scenario['product']['skus'][0]['skuImageUrl'],'https://fake/upload1')
            self.assertTrue(scenario['result']['content_validation']['ok'])
            self.assertEqual(scenario['result']['status'],'PARTIALLY_AUTO_FIXED')


if __name__=='__main__':unittest.main()
