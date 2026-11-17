import unittest
from mye_c_automation.policy_engine import evaluate
from mye_c_automation.audit_one import _definitely_dead

class BusinessMatrix(unittest.TestCase):
    def test_watermark_sop(self):
        cases={'manufacturer_branding':'KEEP','official_marketing_text':'KEEP','social_account_signature':'KEEP','photographer_credit':'KEEP','third_party_store_logo':'REMOVE_CANDIDATE','third_party_store_banner':'REMOVE_CANDIDATE','chinese_promotion_poster':'NEEDS_REVIEW','marketing_text':'NEEDS_REVIEW'}
        for classification,expected in cases.items():
            with self.subTest(classification=classification):
                self.assertEqual(evaluate({'results':[{'task_type':'watermark','classification':classification,'confidence':.99}]}),expected)
    def test_uncertain_judgements_never_keep(self):
        for result in ({'status':'NEEDS_REVIEW'},{'results':[]},{'results':[{'confidence':.5,'task_type':'watermark','classification':'manufacturer_branding'}]}):
            self.assertEqual(evaluate(result),'NEEDS_REVIEW')
    def test_sku_packaging_protection(self):
        for extra,expected in [({'image_type':'product_only','shared_across_skus':True},'KEEP'),({'image_type':'box','shared_across_skus':True},'NEEDS_REVIEW'),({'missing_image':True},'NEEDS_REVIEW'),({'image_type':'box','sku_packaging':'without_box'},'NEEDS_REVIEW'),({'image_type':'product_only','sku_packaging':'with_box'},'NEEDS_REVIEW')]:
            row=dict(task_type='sku_match',confidence=.99,decision='MATCH',**extra)
            self.assertEqual(evaluate({'results':[row]}),expected)
    def test_description_http_status(self):
        for code in (404,410): self.assertTrue(_definitely_dead(code))
        for code in (403,405,500,'timeout','DNS'): self.assertFalse(_definitely_dead(code))
    def test_model_disagreement_reviews(self):
        self.assertEqual(evaluate({'results':[{'task_type':'watermark','confidence':.99,'classification':c} for c in ('manufacturer_branding','third_party_store_logo')]}),'NEEDS_REVIEW')

if __name__=='__main__': unittest.main()
