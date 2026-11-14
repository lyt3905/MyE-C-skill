import unittest
from semantic_remedies import build

class SemanticFailureIsolationTests(unittest.TestCase):
    def test_optional_quality_failure_defers_only_semantic_items(self):
        class Broken:
            def validate_title(self,*args):raise RuntimeError('model unavailable')
            def observe_image(self,*args):raise RuntimeError('OCR unavailable')
        product={'title':'NA-H74 威震天','titleEn':'Old','identityJson':{'modelCode':'NA-H74'},'skus':[{'skuId':1,'skuName':'without box','skuImageUrl':'https://x/a'}]}
        flags={'anomalies':[{'type':'title_prefix'}]}
        rows,handled,resolved=build(product,flags,[],[{'file':'unused.png','url':'https://x/a'}],Broken(),7)
        self.assertNotIn('title_prefix',handled)
        self.assertTrue(rows);self.assertTrue(all(r['action']=='WEB_DEFER' for r in rows))
    def test_E18_independent_role_conflict_never_authorizes_title(self):
        class Conflicting:
            def validate_title(self,*args):return {'ok':False,'reason':'ROLE_CONFLICT','evidence_ids':['DUAL_ROLE_CONFLICT']}
        product={'title':'NA-H74 威震天','titleEn':'Existing','identityJson':{'modelCode':'NA-H74'},'skus':[]}
        rows,handled,_=build(product,{'anomalies':[{'type':'title_prefix'}]},[],[],Conflicting(),7)
        self.assertFalse(any(r['action']=='TITLE_REWRITE' for r in rows))
        self.assertNotIn('title_prefix',handled)
        self.assertEqual(product['titleEn'],'Existing')
