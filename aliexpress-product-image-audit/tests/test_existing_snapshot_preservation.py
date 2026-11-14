import copy
import unittest
from final_state import pre_apply_validate


class ExistingSnapshotPreservationTests(unittest.TestCase):
    def snapshot(self):
        return {'id': 1, 'images': {'main': ['https://test/m'], 'detail': ['https://test/d'], 'sku': ['https://test/s'], 'gallery': [], 'ai': [], 'scene': [], 'attachList': []}, 'skus': [{'skuName': 'with box', 'skuImageUrl': 'https://test/legacy'}], 'status': 'PENDING'}

    def test_unmodified_optional_pools_and_legacy_reference_are_preserved(self):
        before = self.snapshot()
        result = pre_apply_validate(before, {'desired': {'titleEn': 'Hot Sale Toy'}, 'post_actions': {}})
        self.assertTrue(result['ok'])
        self.assertEqual(result['warnings'][0]['rule_id'], 'LEGACY_SKU_REFERENCE_UNCHANGED')

    def test_new_orphan_reference_and_removing_previously_pooled_reference_fail(self):
        before = self.snapshot()
        after = copy.deepcopy(before['skus']); after[0]['skuImageUrl'] = 'https://test/new'
        self.assertFalse(pre_apply_validate(before, {'desired': {'skus': after}, 'post_actions': {}})['ok'])
        before['images']['sku'].append('https://test/legacy')
        changed = copy.deepcopy(before['images']); changed['sku'].remove('https://test/legacy')
        self.assertFalse(pre_apply_validate(before, {'desired': {'images': changed}, 'post_actions': {}})['ok'])

    def test_emptying_previously_populated_pool_fails(self):
        before = self.snapshot(); changed = copy.deepcopy(before['images']); changed['detail'] = []
        self.assertFalse(pre_apply_validate(before, {'desired': {'images': changed}, 'post_actions': {}})['ok'])
