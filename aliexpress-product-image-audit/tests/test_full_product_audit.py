import hashlib
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json
from PIL import Image

from full_product_audit import build_inventory, assemble_report, build_queue
from watermark_fixtures import exhaustive,identity


class FullProductAuditTests(unittest.TestCase):
    def fixture(self,root):
        product={'id':1,'identityJson':{'modelCode':'DW-ES09T'},
                 'images':{'main':['https://x/a','https://x/b'],'detail':['https://x/a'],
                           'sku':['https://x/a','https://x/b'],'ai':['https://forbidden/ai']},
                 'skus':[{'id':None,'skuName':'no retail box','skuImageUrl':'https://x/b'},
                         {'id':None,'skuName':'with retail box','skuImageUrl':'https://x/a'}],
                 'descriptionJson':'opaque https://forbidden/description','price':123}
        raw=[]
        for index,color in enumerate(('red','blue')):
            path=Path(root)/f'{color}.png';Image.new('RGB',(800,800),color).save(path)
            raw.append({'file':str(path),'url':f'https://x/{chr(97+index)}','kind':'main','index':index,
                        'content_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'ocr':[]})
        return product,raw

    def decisions(self,inventory):
        results={}
        for digest in inventory['contents']:
            key='WM_'+digest[:16]
            results[key]={'status':'CLEAN','results':[deepcopy({'task_type':'watermark','classification':'product_print','confidence':.99,
                'abstain':False,'evidence_ids':[key],'marks':[{'classification':'product_print','owner':'factory',
                'location':'bottom','confidence':.99}]}) for _ in range(2)]}
            key='IDENTITY_'+digest[:16]
            results[key]={'status':'CLEAN','results':[deepcopy({'decision':'MATCH','confidence':.99,'abstain':False,
                'model':'DW-ES09T','image_type':'FIGURE','color':'red','model_evidence_ids':[key],'evidence_ids':[key]}) for _ in range(2)]}
        for row in inventory['occurrences']:
            if row['target_type']=='sku_reference':
                key=row['id']
                results[key]={'status':'CLEAN','results':[{'decision':'MATCH','confidence':.99,
                    'abstain':False,'evidence_ids':[key],'image_type':'product_only',
                    'sku_packaging':'without_box' if row['sku_row_index']==0 else 'with_box',
                    'missing_image':False,'shared_across_skus':False}]*2}
        for key,value in results.items():
            if key.startswith('WM_'):value['results']=[exhaustive(dict(row,item_id=key)) for row in value['results']]
            elif key.startswith('IDENTITY_'):value['results']=[identity(dict(row,task_type='product_identity',item_id=key)) for row in value['results']]
        return results

    def test_every_slot_and_sku_reference_is_included_without_machine_triggers(self):
        with tempfile.TemporaryDirectory() as root:
            product,raw=self.fixture(root);inventory=build_inventory(product,raw)
            self.assertEqual(len(inventory['occurrences']),7)
            self.assertEqual(len(inventory['contents']),2)
            self.assertEqual({r['id'] for r in inventory['occurrences']},
                             {'MAIN_000','MAIN_001','DETAIL_000','SKU_000','SKU_001','SKU_ROW_000','SKU_ROW_001'})
            self.assertNotIn('https://forbidden/ai',str(inventory))
            self.assertNotIn('https://forbidden/description',str(inventory))

    def test_only_exact_sha_deduplicates_inference_not_business_positions(self):
        with tempfile.TemporaryDirectory() as root:
            product,raw=self.fixture(root);inventory=build_inventory(product,raw)
            queue=build_queue(product,inventory,Path(root))
            self.assertEqual(len(queue['items']),6)  # 2 ownership + 2 identity + 2 SKU.
            self.assertEqual(len([x for x in queue['items'] if x['task_type']=='watermark']),2)

    def test_missing_result_prevents_audit_complete(self):
        with tempfile.TemporaryDirectory() as root:
            product,raw=self.fixture(root);inventory=build_inventory(product,raw)
            results=self.decisions(inventory);results.pop(next(iter(results)))
            report=assemble_report(product,inventory,results,[])
            self.assertFalse(report['audit_complete'])
            self.assertGreater(report['unresolved_count'],0)

    def test_confirmed_violation_completes_audit_but_never_means_compliant(self):
        with tempfile.TemporaryDirectory() as root:
            product,raw=self.fixture(root);inventory=build_inventory(product,raw);results=self.decisions(inventory)
            key=next(k for k in results if k.startswith('WM_'))
            for row in results[key]['results']:
                row['classification']='third_party_store_banner';row['marks'][0]['classification']='third_party_store_banner'
                row['marks'][0]['owner']='Example Store'
            results[key]['status']='HIT'
            report=assemble_report(product,inventory,results,[])
            self.assertTrue(report['audit_complete'])
            self.assertEqual(report['compliance_status'],'NON_COMPLIANT')
            self.assertFalse(report['remediation_executed'])

    def test_low_confidence_or_abstention_does_not_become_a_clear_failure(self):
        with tempfile.TemporaryDirectory() as root:
            product,raw=self.fixture(root);inventory=build_inventory(product,raw);results=self.decisions(inventory)
            key=next(iter(results));results[key]['results'][0]['confidence']=.79
            report=assemble_report(product,inventory,results,[])
            self.assertFalse(report['audit_complete'])

    def test_confirmed_store_violation_survives_unresolved_auxiliary_marks(self):
        with tempfile.TemporaryDirectory() as root:
            product,raw=self.fixture(root);inventory=build_inventory(product,raw);results=self.decisions(inventory)
            key=next(iter(results))
            for row in results[key]['results']:
                row.update(classification='third_party_store_banner',owner='store',location='top')
                row['marks'][0].update(classification='third_party_store_banner',owner='Example Store')
                row['marks'].append({'mark_id':'M2','classification':'unknown','owner':'unknown','location':'bottom','confidence':.4,
                                     'abstain':True,'bbox_xyxy':[20,400,100,440],'evidence_ids':[key]})
            report=assemble_report(product,inventory,results,[])
            self.assertFalse(report['audit_complete'])
            self.assertEqual(report['compliance_status'],'NON_COMPLIANT')
            occurrence=report['occurrences'][0]
            self.assertEqual(occurrence['checks']['watermark'],'UNKNOWN')
            self.assertEqual(occurrence['confirmed_findings'][0]['rule'],'store_watermark')

    def test_low_confidence_store_roots_never_create_confirmed_findings(self):
        with tempfile.TemporaryDirectory() as root:
            product,raw=self.fixture(root);inventory=build_inventory(product,raw);results=self.decisions(inventory)
            key=next(iter(results))
            for row in results[key]['results']:
                row.update(classification='third_party_store_banner',owner='store',location='top',confidence=.79)
            report=assemble_report(product,inventory,results,[])
            self.assertNotEqual(report['compliance_status'],'NON_COMPLIANT')
            self.assertFalse(report['occurrences'][0].get('confirmed_findings'))

    def test_source_sha_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            product,raw=self.fixture(root);raw[0]['content_sha256']='0'*64
            with self.assertRaisesRegex(ValueError,'SOURCE_SHA_CHANGED'):build_inventory(product,raw)

    def test_missing_reference_remains_a_distinct_unresolved_item(self):
        with tempfile.TemporaryDirectory() as root:
            product,raw=self.fixture(root);product['skus'][0]['skuImageUrl']='https://x/missing'
            inventory=build_inventory(product,raw)
            row=next(r for r in inventory['occurrences'] if r['id']=='SKU_ROW_000')
            self.assertIsNone(row['sha256'])
            self.assertEqual(row['source_status'],'UNVERIFIED')

    def test_identity_requires_observed_model_and_bound_reference(self):
        with tempfile.TemporaryDirectory() as root:
            product,raw=self.fixture(root);inventory=build_inventory(product,raw);results=self.decisions(inventory)
            key=next(k for k in results if k.startswith('IDENTITY_'))
            for row in results[key]['results']:
                row.pop('model_evidence_ids')
                row['observations']['model_identity']['evidence_ids']=[]
            self.assertFalse(assemble_report(product,inventory,results,[])['audit_complete'])

    def test_source_text_annotations_reach_models_without_description_or_prices(self):
        from ai_judge.client import safe_payload
        item={'id':'x','task_type':'product_identity','observed_text_regions':[{'text':'DW-ES09T','score':.996,'rect':[0,0,10,10]}],
              'reference_text_regions':[{'text':'DW-ES09T','score':.996,'rect':[0,0,10,10]}],
              'descriptionJson':'forbidden','price':123}
        payload=safe_payload(item,{'descriptionJson':'forbidden','price':123})
        self.assertEqual(payload['item']['observed_text_regions'],item['observed_text_regions'])
        self.assertEqual(payload['item']['reference_text_regions'],item['reference_text_regions'])
        self.assertNotIn('forbidden',str(payload));self.assertNotIn('123',str(payload))

    def test_unknown_color_does_not_count_as_full_identity_audit(self):
        with tempfile.TemporaryDirectory() as root:
            product,raw=self.fixture(root);inventory=build_inventory(product,raw);results=self.decisions(inventory)
            key=next(k for k in results if k.startswith('IDENTITY_'))
            for row in results[key]['results']:row['color']='unknown'
            self.assertFalse(assemble_report(product,inventory,results,[])['audit_complete'])

    def test_fake_full_workflow_covers_all_positions_with_no_writer(self):
        from full_product_audit import run_full_audit
        from job_manager import atomic_json
        with tempfile.TemporaryDirectory() as root:
            product,raw=self.fixture(root)
            class Reader:
                def current_shop(self):return 7
                def account_fingerprint(self):return 'a'*64
                def product(self,pid):return deepcopy(product)
                def save(self,*args,**kwargs):raise AssertionError('read-only audit must not save')
            def auditor(pid,shop,output_dir,site):
                atomic_json(output_dir/'audit_product.json',product)
                atomic_json(output_dir/'audit_raw.json',{'pid':pid,'images':raw})
                atomic_json(output_dir/'audit_flags.json',{'pid':pid,'summary':{'ocr_enabled':True},'duplicates':[],'anomalies':[]})
            expected=self.decisions(build_inventory(product,raw))
            class Judge:
                models=('a','b')
                metrics={'requests':0,'total_tokens':0,'usage_available':True,'calls':[]}
                def process_queue(self,queue,context):
                    assert all(r['task_type']!='title_semantics' for r in queue['items'])
                    assert 'descriptionJson' not in context and 'price' not in context
                    return expected
            templates=Path(root)/'templates.json'
            atomic_json(templates,{'required_shop_ids':[],'no_applicable_shop_ids':[7],'templates':[]})
            result=run_full_audit(Path(root)/'jobs',1,7,Reader(),judge=Judge(),auditor=auditor,template_config=templates,image_workflow='legacy')
            self.assertTrue(result['audit_complete'])
            self.assertEqual(result['image_and_reference_count'],7)
            self.assertEqual(result['site_save_calls'],0)

    def test_standard_cli_full_audit_constructs_only_a_readonly_client(self):
        import workflow_runner
        with tempfile.TemporaryDirectory() as root:
            root=Path(root)
            (root/'site.json').write_text(json.dumps({'base':'https://fake','user':'fake','pwd':'fake'}))
            (root/'model.json').write_text(json.dumps({'schema':'model-gateway/v1','base_url':'http://127.0.0.1:3425/v1',
                'models':['a','b'],'max_output_tokens':8192,'timeout':150,'retries':0}))
            args=['workflow_runner.py','full-audit','--pid','1','--shop','7','--site-config',str(root/'site.json'),
                  '--model-config',str(root/'model.json'),'--template-config',str(root/'templates.json'),'--root',str(root/'jobs')]
            with patch('sys.argv',args),patch('site_client.ReadOnlySiteClient') as reader, \
                 patch('site_client._SiteTransport') as transport, \
                 patch('full_product_audit.run_full_audit',return_value={'audit_complete':False,'job_id':'test'}) as run:
                workflow_runner.main()
                reader.assert_called_once();transport.assert_not_called();run.assert_called_once()

    def test_shared_mixed_packaging_never_passes(self):
        from full_product_audit import _sku
        rows=[{'decision':'MATCH','confidence':.99,'abstain':False,'image_type':'mixed',
               'sku_packaging':'with_box','missing_image':False,'shared_across_skus':True} for _ in range(2)]
        self.assertNotEqual(_sku({'results':rows},'with retail box',True),'PASS')

    def test_conflicting_primary_colors_never_pass_identity(self):
        from full_product_audit import _identity
        rows=[{'decision':'MATCH','confidence':.99,'abstain':False,'image_type':'FIGURE',
               'model':'DW-ES09T','color':color,'model_evidence_ids':['a'],'evidence_ids':['a']} for color in ('red with black trim','blue with black trim')]
        self.assertEqual(_identity({'results':rows},'DW-ES09T'),'UNKNOWN')

    def test_known_exact_duplicate_is_failure_not_unresolved_near_duplicate(self):
        from full_product_audit import machine_checks
        with tempfile.TemporaryDirectory() as root:
            product,raw=self.fixture(root);product['images']['main'][1]=product['images']['main'][0]
            inventory=build_inventory(product,raw);results=self.decisions(inventory)
            checks=machine_checks(product,inventory,{'duplicates':[{'a':0,'b':1}],'anomalies':[]})
            report=assemble_report(product,inventory,results,checks)
            self.assertTrue(report['audit_complete']);self.assertEqual(report['compliance_status'],'NON_COMPLIANT')

    def test_missing_detail_is_explicit_noncompliance_not_unknown(self):
        from full_product_audit import machine_checks
        with tempfile.TemporaryDirectory() as root:
            product,raw=self.fixture(root);product['images']['detail']=[]
            inventory=build_inventory(product,raw);results=self.decisions(inventory)
            checks=machine_checks(product,inventory,{'duplicates':[],'anomalies':[{'type':'no_detail_images'}]})
            report=assemble_report(product,inventory,results,checks)
            self.assertTrue(report['audit_complete']);self.assertEqual(report['compliance_status'],'NON_COMPLIANT')

    def test_identity_observed_aliases_normalize_without_inventing_values(self):
        from ai_judge.schemas import validate_result
        row={'task_type':'product_identity','item_id':'a','decision':'MATCH','confidence':.93,
             'abstain':False,'evidence_ids':['a'],'observed_model':'DW-ES09T',
             'observed_color':'green and purple','model_evidence_ids':['a']}
        result=validate_result(row,'product_identity','a')
        self.assertEqual(result['model'],row['observed_model']);self.assertEqual(result['color'],row['observed_color'])
        self.assertEqual(result['confidence'],.93)
        with self.assertRaises(ValueError):validate_result(dict(row,model='OTHER'),'product_identity','a')
