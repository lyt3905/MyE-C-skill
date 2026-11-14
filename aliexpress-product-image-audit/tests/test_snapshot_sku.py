import unittest
import tempfile
import json
from pathlib import Path
from copy import deepcopy
from sku_assignment import plan_assignments


class SnapshotSkuTests(unittest.TestCase):
    def fixture(self):
        product={'identityJson':{'modelCode':'NA-H74'},
                 'images':{'main':['https://x/box'],'detail':['https://x/body'],'sku':['https://x/box']},
                 'skus':[{'id':None,'skuName':'no retail box','originalBox':False,'skuImageUrl':'https://x/box','price':10},
                         {'id':None,'skuName':'with retail box','originalBox':True,'skuImageUrl':'https://x/box','price':12}]}
        observations=[{'url':'https://x/body','verified':True,'clean':True,'model':'NA-H74',
                       'image_type':'FIGURE','sha256':'a'*64,'evidence_ids':['BODY']},
                      {'url':'https://x/box','verified':True,'clean':True,'model':'NA-H74',
                       'image_type':'BOX','sha256':'b'*64,'evidence_ids':['BOX']}]
        return product,observations

    def test_opt_in_uses_snapshot_locator_without_inventing_ids(self):
        from snapshot_sku import validate_assignments
        product,images=self.fixture();before=deepcopy(product)
        result=plan_assignments(product,images,allow_snapshot_rows=True)
        self.assertEqual(result['assignments'],{})
        self.assertEqual(len(result['row_assignments']),1)
        row=result['row_assignments'][0]
        self.assertEqual(row['index'],0)
        self.assertEqual(row['url'],'https://x/body')
        self.assertEqual(len(row['source_sha256']),64)
        validate_assignments(product,result['row_assignments'])
        self.assertEqual(product,before)

    def test_reordered_or_edited_rows_reject_the_original_locator(self):
        from snapshot_sku import validate_assignments
        product,images=self.fixture()
        rows=plan_assignments(product,images,allow_snapshot_rows=True)['row_assignments']
        for change in ('reorder','price','packaging'):
            changed=deepcopy(product)
            if change=='reorder':changed['skus'].reverse()
            if change=='price':changed['skus'][0]['price']=11
            if change=='packaging':changed['skus'][0]['skuName']='with retail box'
            with self.subTest(change=change),self.assertRaises(ValueError):validate_assignments(changed,rows)

    def test_ambiguous_packaging_does_not_gain_row_assignments(self):
        product,images=self.fixture();product['skus'][1]['skuName']='no retail box';product['skus'][1]['originalBox']=False
        result=plan_assignments(product,images,allow_snapshot_rows=True)
        self.assertFalse(result.get('row_assignments'))
        self.assertFalse(result['assignments'])

    def test_default_still_defers_missing_ids(self):
        product,images=self.fixture()
        result=plan_assignments(product,images)
        self.assertFalse(result['assignments'])
        self.assertFalse(result.get('row_assignments'))

    def test_partial_failure_identifies_the_actual_row_with_no_ids(self):
        product,images=self.fixture();product['skus'][1]['modelCode']='OTHER-99'
        result=plan_assignments(product,images,allow_snapshot_rows=True)
        self.assertEqual(result['deferred_rows'],[{'index':1,'reason':'SKU_MODEL_CONFLICT'}])
        self.assertEqual([entry['index'] for entry in result['row_assignments']],[0])

    def test_unverified_existing_with_box_reference_is_preserved(self):
        product,images=self.fixture()
        result=plan_assignments(product,images[:1],allow_snapshot_rows=True)
        self.assertEqual([entry['index'] for entry in result['row_assignments']],[0])
        self.assertEqual(result['deferred_rows'],[{'index':1,'reason':'SKU_EXISTING_REFERENCE_UNVERIFIED'}])

    def test_identical_content_at_two_urls_is_one_image_choice(self):
        product,images=self.fixture()
        product['images']['detail'].append('https://x/body-copy')
        images.append(dict(images[0],url='https://x/body-copy'))
        result=plan_assignments(product,images,allow_snapshot_rows=True)
        self.assertEqual(len(result['row_assignments']),1)
        self.assertEqual(result['row_assignments'][0]['url'],'https://x/body')

    def test_fake_workflow_saves_bound_row_and_verifies_downloaded_image(self):
        from test_auto_semantic_workflow import SemanticWorkflowTests
        with tempfile.TemporaryDirectory() as root:
            result,writer,product=SemanticWorkflowTests().execute_case(root,'sku',snapshot_rows=True)
            self.assertEqual(result['status'],'AUTO_VERIFIED',result)
            self.assertEqual(writer.saves,1)
            self.assertEqual(product['skus'][0]['skuImageUrl'],'https://x/body')
            self.assertEqual(product['skus'][1]['skuImageUrl'],'https://x/box')
            self.assertTrue(all(row.get('id') is None and 'skuId' not in row for row in product['skus']))
            directory=next(Path(root).glob('JOB_*'))
            plan=json.loads((directory/'plan.v2.json').read_text(encoding='utf-8'))
            self.assertNotIn('sku_assignments',plan['post_actions'])
            self.assertEqual(plan['post_actions']['sku_row_assignments'][0]['index'],0)
            proof=json.loads((directory/'content_validation.json').read_text(encoding='utf-8'))
            self.assertTrue(proof['ok'])
            from jsonschema import Draft202012Validator
            schemas=Path(__file__).resolve().parents[1]/'scripts/config/schemas'
            validator=Draft202012Validator(json.loads((schemas/'plan.v3.schema.json').read_text(encoding='utf-8')))
            self.assertEqual(list(validator.iter_errors(plan)),[])
            validator=Draft202012Validator(json.loads((schemas/'remedy-candidate.v1.schema.json').read_text(encoding='utf-8')))
            for row in json.loads((directory/'remedy_candidates.json').read_text(encoding='utf-8'))['items']:
                self.assertEqual(list(validator.iter_errors(row)),[])

    def test_saved_row_reorder_or_price_drift_stops_without_retry(self):
        from test_auto_semantic_workflow import SemanticWorkflowTests
        for drift in ('reorder','price'):
            with self.subTest(drift=drift),tempfile.TemporaryDirectory() as root:
                with self.assertRaisesRegex(ValueError,'post-write verification failed'):
                    SemanticWorkflowTests().execute_case(root,'sku',snapshot_rows=True,snapshot_readback=drift)
                directory=next(Path(root).glob('JOB_*'))
                self.assertFalse((directory/'apply_receipt.json').exists())
                self.assertEqual(json.loads((directory/'save_attempt.json').read_text())['site_save_calls'],1)
                self.assertEqual(json.loads((directory/'local_execution.json').read_text())['state'],'APPLY_UNKNOWN')
                self.assertFalse(json.loads((directory/'recovery_readback.json').read_text())['retry_save_allowed'])

    def test_disabled_policy_cannot_execute_snapshot_post_action(self):
        from executor.local import LocalExecutor
        from automation_policy import AutomationPolicy
        from test_auto_decision import CONFIG
        with tempfile.TemporaryDirectory() as root:
            class Writer:
                def save(self,*args,**kwargs):raise AssertionError('must not save')
            plan={'post_actions':{'sku_row_assignments':[{'index':0}]}}
            with self.assertRaisesRegex(ValueError,'SNAPSHOT_SKU_ASSIGNMENT_NOT_AUTHORIZED'):
                LocalExecutor(Writer(),root).execute_auto(plan,AutomationPolicy(CONFIG))

    def test_duplicate_indices_or_unbound_urls_are_rejected(self):
        from snapshot_sku import validate_assignments
        product,images=self.fixture()
        entries=plan_assignments(product,images,allow_snapshot_rows=True)['row_assignments']
        with self.assertRaises(ValueError):validate_assignments(product,entries+entries)
        bad=deepcopy(entries);bad[0]['url']='https://unverified.invalid/image'
        with self.assertRaises(ValueError):validate_assignments(product,bad)
