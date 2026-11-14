import unittest
from workflow_v2_pipeline import semantic_candidates

class SemanticIdentityTests(unittest.TestCase):
    def test_sku_and_identity_requests_use_business_ids(self):
        product={'identityReviewRequired':True,'skus':[{'skuId':1,'skuName':'without box','skuImageUrl':'https://x/a','semanticReviewRequired':True}]}
        row={'kind':'main','index':2,'url':'https://x/a','file':'C:/private/image.jpg','content_sha256':'a'*64}
        items=semantic_candidates(product,{},[row])
        self.assertEqual([r['image_id'] for r in items],['MAIN_002','MAIN_002'])
        self.assertEqual(items[0]['source_url'],'https://x/a')
        self.assertEqual(items[0]['pool'],'main')
