import unittest
import hashlib
from sku_assignment import plan_assignments

class SkuAssignmentTests(unittest.TestCase):
    def test_numeric_pack_contents_need_per_sku_proof(self):
        for spec in ('2-pack','2 pack','10-pack','1-pack'):
            with self.subTest(spec=spec):
                product=self.product();product['skus'][0]['skuName']='without box '+spec
                result=plan_assignments(product,[self.image('https://x/box','BOX'),self.image('https://x/body','FIGURE')])
                if spec=='1-pack':self.assertEqual(result['assignments']['1'],'https://x/body')
                else:
                    self.assertNotIn('1',result['assignments'])
                    self.assertEqual(result['deferred_reasons']['1'],'SKU_COMPLEX_CONTENTS_UNVERIFIED')
    def test_bundle_content_needs_more_than_generic_model_packaging_observation(self):
        complex_names=('combo bundle without box','figure set without box','2pcs without box','accessory pack without box','pack of 10 without box','2件套 无盒')
        for name in complex_names+('1pc without box','without retail box','stock package without box','sunset figure without box'):
            product=self.product();product['skus'][0]['skuName']=name
            result=plan_assignments(product,[self.image('https://x/box','BOX'),self.image('https://x/body','FIGURE')])
            if name in complex_names:self.assertIn('1',result['deferred']);self.assertNotIn('1',result['assignments'])
            else:self.assertEqual(result['assignments']['1'],'https://x/body')
    def test_explicit_sku_model_conflict_defers_but_compact_aliases_remain_valid(self):
        for model in ('MS-01','NAH74','NA H74'):
            product=self.product();product['skus'][0]['modelCode']=model
            result=plan_assignments(product,[self.image('https://x/box','BOX'),self.image('https://x/body','FIGURE')])
            if model=='MS-01':
                self.assertNotIn('1',result['assignments']);self.assertIn('1',result['deferred'])
            else:self.assertEqual(result['assignments']['1'],'https://x/body')
    def image(self,url,kind,model='NA-H74'):
        return {'url':url,'image_type':kind,'model':model,'clean':True,'verified':True,'sha256':hashlib.sha256(url.encode()).hexdigest(),'evidence_ids':['SKU_MODEL_1']}
    def product(self,url='https://x/box'):
        return {'identityJson':{'modelCode':'NA-H74'},'skus':[{'skuId':1,'skuName':'without box','skuImageUrl':url,'price':10},{'skuId':2,'skuName':'with box','skuImageUrl':url,'price':12}]}
    def test_shared_body_requires_no_change(self):
        result=plan_assignments(self.product('https://x/body'),[self.image('https://x/body','FIGURE')])
        self.assertEqual(result['assignments'],{});self.assertFalse(result['deferred'])
    def test_shared_box_reassigns_without_box_only(self):
        result=plan_assignments(self.product(),[self.image('https://x/box','BOX'),self.image('https://x/body','FIGURE')])
        self.assertEqual(result['assignments'],{'1':'https://x/body'})
    def test_without_box_has_no_valid_source(self):
        result=plan_assignments(self.product(),[self.image('https://x/box','BOX')])
        self.assertFalse(result['assignments']);self.assertEqual(result['deferred'],['1'])
    def test_wrong_model_and_ambiguous_sources_defer(self):
        for images in ([self.image('https://x/wrong','FIGURE','MS-01')],[self.image('https://x/a','FIGURE'),self.image('https://x/b','FIGURE')]):
            result=plan_assignments(self.product(),images)
            self.assertFalse(result['assignments']);self.assertIn('1',result['deferred'])
    def test_missing_model_or_verification_defer(self):
        image=self.image('https://x/body','FIGURE');image['verified']=False
        self.assertFalse(plan_assignments(self.product(),[image])['assignments'])
    def test_E14_conflicting_sku_color_never_assigns_other_color(self):
        product=self.product();product['skus'][0]['color']='red'
        wrong=self.image('https://x/blue','FIGURE');wrong['color']='blue'
        result=plan_assignments(product,[self.image('https://x/box','BOX'),wrong])
        self.assertNotIn('1',result['assignments']);self.assertIn('1',result['deferred'])
