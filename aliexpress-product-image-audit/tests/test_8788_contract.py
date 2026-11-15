import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from ai_judge.schemas import validate_result
from ai_judge.cache import cache_key


def evidence():
    return {'id':'WM_X','task_type':'watermark','dimensions':[800,800],'evidence_ids':['WM_X','OCR_X']}


def mark(kind='product_print',box=None,confidence=.97,owner='Dr Wu'):
    return {'mark_id':'M1','classification':kind,'owner':owner,'location':'top',
            'bbox_xyxy':box or [10,10,500,80],'confidence':confidence,'abstain':False,'evidence_ids':['WM_X']}


def response(marks=None,no_marks=False):
    return {'schema_version':'watermark/v3','task_type':'watermark','item_id':'WM_X',
            'confidence':.98,'abstain':False,'image_size':[800,800],
            'coverage_complete':True,'no_marks_detected':no_marks,
            'marks':deepcopy(marks if marks is not None else [mark()]),
            'unresolved_items':[],'evidence_ids':['WM_X']}


def pair(a,b=None):return {'results':[deepcopy(a),deepcopy(a if b is None else b)]}


class WatermarkV3Tests(unittest.TestCase):
    def aggregate(self,a,b=None,**kwargs):
        from ai_judge.watermark_contract import aggregate_watermarks
        return aggregate_watermarks(pair(a,b),evidence(),**kwargs)

    def test_schema_requires_exhaustive_fields(self):
        row=response();row.pop('coverage_complete')
        with self.assertRaises(ValueError):validate_result(row,'watermark','WM_X',evidence())

    def test_schema_rejects_invalid_boxes_and_unbound_evidence(self):
        for box in ([0,0,801,50],[20,20,10,30],[False,0,30,40],[0,0,float('nan'),30],None):
            with self.subTest(box=box):
                row=response();row['marks'][0]['bbox_xyxy']=box
                with self.assertRaises(ValueError):validate_result(row,'watermark','WM_X',evidence())
        row=response();row['marks'][0]['evidence_ids']=['OTHER']
        with self.assertRaises(ValueError):validate_result(row,'watermark','WM_X',evidence())

    def test_image_size_must_match_original(self):
        row=response();row['image_size']=[1000,1000]
        with self.assertRaises(ValueError):validate_result(row,'watermark','WM_X',evidence())

    def test_aggregator_rejects_result_bound_to_another_item(self):
        row=response();row['item_id']='OTHER'
        self.assertNotEqual(self.aggregate(row)['review_status'],'PASS')

    def test_same_provider_cannot_count_as_two_models(self):
        from ai_judge.watermark_contract import aggregate_watermarks
        result=pair(response());result['models']=['a','a']
        self.assertNotEqual(aggregate_watermarks(result,evidence())['review_status'],'PASS')

    def test_removal_subtype_conflict_is_unknown_for_new_regions(self):
        a=response([mark('third_party_store_banner',owner='Example Store')])
        b=response([mark('third_party_store_logo',owner='Example Store')])
        result=self.aggregate(a,b)
        self.assertEqual(result['review_status'],'UNKNOWN');self.assertFalse(result['confirmed_findings'])

    def test_confirmed_banner_survives_unknown_small_print(self):
        a=response([mark('third_party_store_banner',owner='Example Store'),mark('unknown',[10,400,100,440],.4,owner='unknown')])
        a['marks'][1]['mark_id']='M2'
        result=self.aggregate(a)
        self.assertEqual(result['review_status'],'PARTIAL')
        self.assertEqual(len(result['confirmed_findings']),1)
        self.assertTrue(result['unresolved_items'])
        self.assertFalse(result['confirmed_findings'][0]['remediation_authorized'])

    def test_each_protected_class_passes_without_removal(self):
        for kind in ('photographer_credit','social_account_signature','manufacturer_branding','product_print','official_marketing_text'):
            with self.subTest(kind=kind):
                result=self.aggregate(response([mark(kind)]))
                self.assertEqual(result['review_status'],'PASS');self.assertFalse(result['confirmed_findings'])

    def test_no_marks_requires_both_explicit_exhaustive_confirmations(self):
        row=response([],True)
        self.assertEqual(self.aggregate(row)['review_status'],'PASS')
        for field in ('coverage_complete','no_marks_detected'):
            other=deepcopy(row);other.pop(field)
            self.assertNotEqual(self.aggregate(row,other)['review_status'],'PASS')

    def test_root_abstention_preserves_other_model_local_observation(self):
        a=response([],False);a.update(abstain=True,coverage_complete=False)
        result=self.aggregate(a,response([mark('third_party_store_banner',owner='Example Store')]))
        self.assertNotEqual(result['review_status'],'PASS')
        self.assertTrue(result['regions'])
        self.assertIsNotNone(result['regions'][0]['model_b_observation'])

    def test_same_region_class_conflict_does_not_erase_other_region(self):
        a=response([mark('third_party_store_banner',owner='Example Store'),dict(mark(box=[20,400,100,440]),mark_id='M2')])
        b=deepcopy(a);b['marks'][1]['classification']='photographer_credit'
        result=self.aggregate(a,b)
        self.assertEqual(len(result['confirmed_findings']),1)
        self.assertTrue(any(r['status']=='UNKNOWN' for r in result['regions']))

    def test_region_matching_is_independent_of_array_order(self):
        a=response([mark('third_party_store_banner',owner='Example Store'),dict(mark(box=[20,400,100,440]),mark_id='M2')])
        b=deepcopy(a);b['marks'].reverse()
        self.assertEqual(self.aggregate(a,b)['review_status'],'FAIL')
        self.assertEqual(len(self.aggregate(a,b)['regions']),2)

    def test_unmatched_regions_are_not_combined(self):
        a=response([mark()]);b=response([mark(box=[20,500,200,600])])
        result=self.aggregate(a,b)
        self.assertEqual(len(result['regions']),2)
        self.assertEqual(result['review_status'],'UNKNOWN')

    def test_region_threshold_is_configured_and_boundary_tested(self):
        a=response([mark(box=[0,0,200,100])]);b=response([mark(box=[0,0,100,100])])
        self.assertEqual(self.aggregate(a,b,matching={'min_iou':.5})['review_status'],'PASS')
        self.assertEqual(self.aggregate(a,b,matching={'min_iou':.51})['review_status'],'UNKNOWN')

    def test_legacy_roots_preserve_finding_but_not_coverage(self):
        row={'task_type':'watermark','item_id':'WM_X','classification':'third_party_store_banner',
             'owner':'Example Store','location':'top','confidence':.98,'abstain':False,'evidence_ids':['WM_X']}
        result=self.aggregate(row)
        self.assertNotEqual(result['coverage_status'],'COMPLETE')
        self.assertEqual(len(result['confirmed_findings']),1)
        self.assertIn('LEGACY_RESULT_NOT_EXHAUSTIVE',{r['reason_code'] for r in result['unresolved_items']})

    def test_legacy_mark_low_confidence_is_not_hidden_by_format_reason(self):
        row={'task_type':'watermark','item_id':'WM_X','classification':'third_party_store_banner',
             'owner':'Example Store','location':'top','confidence':.98,'abstain':False,'evidence_ids':['WM_X'],
             'marks':[{'classification':'product_print','owner':'factory','location':'box','confidence':.4}]}
        result=self.aggregate(row)
        self.assertEqual(len(result['confirmed_findings']),1)
        self.assertTrue(any(r['reason_code']=='LOW_CONFIDENCE' and r['field']=='marks[0].confidence' for r in result['unresolved_items']))

    def test_legacy_root_category_difference_is_reported_without_region_inference(self):
        a={'task_type':'watermark','item_id':'WM_X','classification':'manufacturer_branding',
           'owner':'factory','location':'box','confidence':.95,'abstain':False,'evidence_ids':['WM_X']}
        b=dict(a,classification='product_print')
        result=self.aggregate(a,b)
        self.assertFalse(result['regions'])
        self.assertTrue(any(r['reason_code']=='MODEL_DISAGREEMENT' and r['field']=='classification' for r in result['unresolved_items']))

    def test_contract_version_changes_cache_key(self):
        from ai_judge import watermark
        old=cache_key('watermark',evidence(),{},'fake')
        with patch.object(watermark,'SCHEMA_VERSION','watermark/future'):
            self.assertNotEqual(old,cache_key('watermark',evidence(),{},'fake'))

    def test_old_root_cache_cannot_satisfy_new_contract(self):
        from ai_judge import JudgeClient
        from budget_manager import BudgetManager
        with tempfile.TemporaryDirectory() as temp:
            old_key=cache_key('watermark',evidence(),{},'a',schema_version='v2')
            Path(temp,old_key+'.json').write_text(json.dumps({'classification':'product_print'}))
            calls=[]
            def fake(*args):
                calls.append(args[0]);return {'choices':[{'message':{'content':json.dumps(response())}}]}
            client=JudgeClient(BudgetManager({'ai_requests':2}),temp,models=('a','b'),transport=fake,retries=0)
            result=client.classify('watermark',evidence(),{})
            self.assertEqual(calls,['a','b']);self.assertEqual(result['status'],'CLEAN')

    def test_missing_original_dimensions_blocks_before_provider_call(self):
        from ai_judge import JudgeClient
        from budget_manager import BudgetManager
        with tempfile.TemporaryDirectory() as temp:
            calls=[];client=JudgeClient(BudgetManager({'ai_requests':2}),temp,transport=lambda *a:calls.append(a))
            result=client.classify('watermark',{'id':'WM_X','evidence_ids':['WM_X']},{})
            self.assertEqual(result.get('error'),'SOURCE_UNVERIFIED')
            self.assertFalse(calls);self.assertEqual(client.metrics['requests'],0)


def identity_result():
    fields={'product_subject':'transforming toy','image_type':'FIGURE','model_identity':'DW-ES09T',
            'color':'green and purple','packaging':'UNBOXED'}
    return {'schema_version':'product-identity/v3','task_type':'product_identity','item_id':'ID_X',
            'decision':'MATCH','confidence':.97,'abstain':False,'evidence_ids':['ID_X'],
            'observations':{k:{'value':v,'decision':'MATCH','confidence':.97,'abstain':False,'evidence_ids':['ID_X'],
                            **({'visibility':'VISIBLE'} if k=='model_identity' else {})} for k,v in fields.items()}}


class IdentityDimensionTests(unittest.TestCase):
    def aggregate(self,a,b=None):
        from ai_judge.identity_contract import aggregate_identity
        return aggregate_identity(pair(a,b),'DW-ES09T',{'id':'ID_X','evidence_ids':['ID_X']})

    def test_model_not_visible_is_unknown_not_mismatch_or_match(self):
        row=identity_result();row['observations']['model_identity'].update(value=None,visibility='NOT_VISIBLE',decision='UNCERTAIN')
        result=self.aggregate(row)
        self.assertEqual(result['dimensions']['model_identity']['status'],'UNKNOWN')
        self.assertIn('MODEL_NOT_VISIBLE',result['dimensions']['model_identity']['reason_codes'])
        self.assertEqual(result['dimensions']['image_type']['status'],'PASS')
        self.assertEqual(result['verdict'],'UNKNOWN')

    def test_box_mixed_conflict_is_separate_from_subject(self):
        a=identity_result();b=deepcopy(a)
        a['observations']['image_type']['value']='BOX';b['observations']['image_type']['value']='MIXED'
        result=self.aggregate(a,b)
        self.assertEqual(result['dimensions']['product_subject']['status'],'PASS')
        self.assertIn('IMAGE_TYPE_CONFLICT',result['dimensions']['image_type']['reason_codes'])

    def test_color_conflict_does_not_erase_subject_or_type(self):
        a=identity_result();b=deepcopy(a);b['observations']['color']['value']='red and black'
        result=self.aggregate(a,b)
        self.assertEqual(result['dimensions']['product_subject']['status'],'PASS')
        self.assertEqual(result['dimensions']['image_type']['status'],'PASS')
        self.assertIn('COLOR_CONFLICT',result['dimensions']['color']['reason_codes'])

    def test_low_dimension_confidence_cannot_be_promoted(self):
        a=identity_result();a['observations']['packaging']['confidence']=.79
        self.assertEqual(self.aggregate(a)['verdict'],'UNKNOWN')

    def test_bound_complete_identity_passes(self):
        row=identity_result();normalized=validate_result(row,'product_identity','ID_X',{'evidence_ids':['ID_X']})
        self.assertEqual(self.aggregate(normalized)['verdict'],'PASS')

    def test_client_does_not_call_legacy_identity_complete(self):
        from ai_judge import JudgeClient
        from budget_manager import BudgetManager
        row={'task_type':'product_identity','item_id':'ID_X','decision':'MATCH','confidence':.99,
             'abstain':False,'evidence_ids':['ID_X'],'model':'DW-ES09T','model_evidence_ids':['ID_X']}
        with tempfile.TemporaryDirectory() as temp:
            client=JudgeClient(BudgetManager({'ai_requests':2}),temp,models=('a','b'),retries=0,
                transport=lambda *a:{'choices':[{'message':{'content':json.dumps(row)}}]})
            result=client.classify('product_identity',{'id':'ID_X','evidence_ids':['ID_X']},{'identityJson':{'modelCode':'DW-ES09T'}})
            self.assertEqual(result['status'],'REVIEW')
            self.assertEqual(result['identity_audit']['dimensions']['model_identity']['status'],'UNKNOWN')

    def test_legacy_root_confidence_is_not_invented_for_each_dimension(self):
        row={'task_type':'product_identity','item_id':'ID_X','decision':'MATCH','confidence':.99,
             'abstain':False,'evidence_ids':['ID_X'],'model':'DW-ES09T','model_evidence_ids':['ID_X'],
             'image_type':'BOX','color':'green'}
        result=self.aggregate(row)
        observation=result['dimensions']['image_type']['model_a_observation']
        self.assertEqual(observation['value'],'BOX')
        self.assertIsNone(observation['confidence'])
        self.assertEqual(observation['legacy_root_confidence'],.99)

    def test_root_identity_disagreement_is_not_hidden_by_dimensions(self):
        a=identity_result();b=deepcopy(a);b['decision']='UNCERTAIN'
        self.assertEqual(self.aggregate(a,b)['verdict'],'UNKNOWN')

    def test_invalid_dimension_is_unknown_instead_of_crashing(self):
        row=identity_result();row['observations']['color']=[]
        self.assertEqual(self.aggregate(row)['verdict'],'UNKNOWN')

    def test_identity_reasons_do_not_mutate_watermark_reasons(self):
        from full_product_audit import assemble_report
        sha='a'*64;wm_id='WM_'+sha[:16];identity_id='IDENTITY_'+sha[:16]
        wm=json.loads(json.dumps(response()).replace('WM_X',wm_id))
        a=json.loads(json.dumps(identity_result()).replace('ID_X',identity_id));b=deepcopy(a)
        b['observations']['color']['value']='red'
        inventory={'contents':{sha:{'width':800,'height':800}},'occurrences':[{'id':'MAIN_000','target_type':'image_slot','pool':'main','index':0,'sha256':sha,'url':'https://fake/a'}]}
        product={'id':1,'identityJson':{'modelCode':'DW-ES09T'},'images':{'main':['https://fake/a'],'detail':['https://fake/a'],'sku':[]},'skus':[]}
        report=assemble_report(product,inventory,{wm_id:pair(wm),identity_id:pair(a,b)},[])
        self.assertFalse(report['occurrences'][0]['watermark_audit']['unresolved_items'])
        self.assertIn('COLOR_CONFLICT',report['occurrences'][0]['unknown_reason_codes'])

    def test_sha_analysis_is_reused_for_each_business_position(self):
        from full_product_audit import assemble_report
        from ai_judge.watermark_contract import aggregate_watermarks
        from ai_judge.identity_contract import aggregate_identity
        sha='b'*64;wm_id='WM_'+sha[:16];identity_id='IDENTITY_'+sha[:16]
        wm=json.loads(json.dumps(response()).replace('WM_X',wm_id))
        identity=json.loads(json.dumps(identity_result()).replace('ID_X',identity_id))
        inventory={'contents':{sha:{'width':800,'height':800}},'occurrences':[
            {'id':pool.upper()+'_000','target_type':'image_slot','pool':pool,'index':0,'sha256':sha,'url':'https://fake/a'} for pool in ('main','detail','sku')]}
        product={'id':1,'identityJson':{'modelCode':'DW-ES09T'},'images':{pool:['https://fake/a'] for pool in ('main','detail','sku')},'skus':[]}
        with patch('ai_judge.watermark_contract.aggregate_watermarks',wraps=aggregate_watermarks) as watermarks,patch('ai_judge.identity_contract.aggregate_identity',wraps=aggregate_identity) as identities:
            report=assemble_report(product,inventory,{wm_id:pair(wm),identity_id:pair(identity)},[])
        self.assertEqual(len(report['occurrences']),3)
        self.assertEqual((watermarks.call_count,identities.call_count),(1,1))
