import unittest
from workflow_v2_pipeline import semantic_candidates
from policy_engine import evaluate
class SemanticQueueTests(unittest.TestCase):
    def test_normal_items_do_not_call_ai(self):
        self.assertEqual(semantic_candidates({'skus':[{'id':'1'}]}, {}, [])[0]['reason'], 'MISSING_IMAGE')
    def test_sku_reference_bound_to_real_image(self):
        product={'skus':[{'id':'s1','imageNameMismatch':True,'imageUrl':'url'}]}
        self.assertEqual(semantic_candidates(product,{},[])[0]['reason'],'MISSING_IMAGE')
        rows=semantic_candidates(product,{},[{'url':'url','file':'sku.jpg','content_sha256':'abc'}])
        self.assertEqual(rows[0]['sku_id'],'s1')
        self.assertEqual(rows[0]['image_id'],'SKU_000')
        self.assertEqual(rows[0]['sha256'],'abc')
    def test_title_semantics_uncertainty_does_not_queue_model_review(self):
        rows=semantic_candidates({'titleEn':'Toy'}, {'anomalies':[{'type':'title_identity_mismatch'}]}, [])
        self.assertEqual(rows,[])
    def test_semantics_mismatch_cannot_authorize_mutation(self):
        result={'status':'HIT','results':[{'task_type':'sku_match','decision':'MISMATCH','confidence':.99,'abstain':False}]}
        self.assertEqual(evaluate(result),'NEEDS_REVIEW')
    def test_low_confidence_never_keep(self):
        self.assertEqual(evaluate({'results':[{'classification':'product_print','confidence':.4}]}),'NEEDS_REVIEW')

    def test_ocr_model_contradiction_creates_candidate(self):
        product={'skus':[{'id':'s','name':'AB-123','imageUrl':'url'}]}
        image={'url':'url','file':'sku.jpg','ocr':[{'text':'CD-456','score':.99}]}
        self.assertEqual(semantic_candidates(product,{},[image])[0]['task_type'],'sku_match')
        image['ocr']=[{'text':'AB-123','score':.99}]
        self.assertEqual(semantic_candidates(product,{},[image]),[])
    def test_policy_values_drive_title_check(self):
        from unittest.mock import patch
        import audit_one
        with patch.dict(audit_one.POLICY, {'shop_title_prefix':{'7':'Prefix'},'title_max_length':3}):
            result=audit_one.title_checks({'titleEn':'Prefix abc'},7)
            self.assertTrue(result['prefix_ok'])
            self.assertIn('title_length',result['anomalies'])
