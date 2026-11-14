import unittest
from copy import deepcopy
import product_state


class PricingReadbackTests(unittest.TestCase):
    def snapshot(self):
        return {'titleEn':'Title','descriptionJson':'opaque {','price':{'costPrice':160,'profitMargin':20},
                'weight':.4,'status':'PENDING','images':{'main':['https://x/a']},
                'skus':[{'skuId':1,'skuName':'with box','skuImageUrl':'https://x/a','skuPrice':332.6,
                         'discountPrice':33.74,'shippingFee':10.02,'quantity':10}]}

    def test_only_derived_sku_amounts_are_excluded_from_postsave_comparison(self):
        before=self.snapshot();after=deepcopy(before)
        after['skus'][0].update(discountPrice=34.24,shippingFee=10.17)
        self.assertNotEqual(product_state.canonical_state_hash(before),product_state.canonical_state_hash(after))
        self.assertTrue(product_state.saved_state_matches(before,after))
        self.assertEqual(before,self.snapshot())
        self.assertEqual(after['skus'][0]['discountPrice'],34.24)

    def test_inputs_identity_description_and_references_stay_strict(self):
        for field,value in [('skuPrice',333),('skuImageUrl','https://x/b'),('skuId',2),('quantity',9),('skuName','without box')]:
            with self.subTest(field=field):
                before=self.snapshot();after=deepcopy(before);after['skus'][0][field]=value
                self.assertFalse(product_state.saved_state_matches(before,after))
        for field,value in [('descriptionJson','other'),('status','EDITING'),('weight',.5),('price',{'costPrice':170})]:
            with self.subTest(field=field):
                before=self.snapshot();after=deepcopy(before);after[field]=value
                self.assertFalse(product_state.saved_state_matches(before,after))

    def test_readback_context_only_does_not_allow_outbound_repricing(self):
        from final_state import validate_final_snapshot
        before=self.snapshot();before['images'].update(detail=['https://x/d'],sku=['https://x/a'])
        after=deepcopy(before);after['skus'][0].update(discountPrice=34.24,shippingFee=10.17)
        self.assertFalse(validate_final_snapshot(after,context={'before':before})['ok'])
        self.assertTrue(validate_final_snapshot(after,context={'before':before,'saved_readback':True})['ok'])
