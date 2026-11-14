import unittest
from copy import deepcopy
from check import verify_snapshot


class LegacySkuDeliveryTests(unittest.TestCase):
    def snapshot(self):
        return {'images': {'main': ['https://x/main'], 'detail': ['https://x/detail'],
                           'sku': ['https://x/sku']},
                'skus': [{'skuId': 1, 'skuImageUrl': 'https://x/detail'}],
                'titleEn': 'Old', 'titleTranslationZh': 'Old translation'}

    def test_without_before_remains_strict(self):
        self.assertFalse(verify_snapshot(self.snapshot())['ok'])

    def test_unchanged_legacy_reference_uses_real_before(self):
        before=self.snapshot();after=deepcopy(before)
        after.update(titleEn='New', titleTranslationZh='New translation')
        result=verify_snapshot(after,before=before)
        self.assertTrue(result['ok'])
        self.assertTrue(any(w['rule_id']=='LEGACY_SKU_REFERENCE_UNCHANGED' for w in result['validation']['warnings']))

    def test_changed_or_new_outside_reference_rejected(self):
        before=self.snapshot()
        for append in (False,True):
            after=deepcopy(before)
            if append:after['skus'].append({'skuId':2,'skuImageUrl':'https://x/new'})
            else:after['skus'][0]['skuImageUrl']='https://x/new'
            self.assertFalse(verify_snapshot(after,before=before)['ok'])

    def test_changed_reference_to_valid_sku_pool_passes(self):
        before=self.snapshot();after=deepcopy(before)
        after['skus'][0]['skuImageUrl']='https://x/sku'
        self.assertTrue(verify_snapshot(after,before=before)['ok'])
