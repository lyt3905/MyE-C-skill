import json
import tempfile
import unittest

from sku_assignment import plan_assignments
import test_v13_account_cli as cli


class MissingSkuIdentityTests(unittest.TestCase):
    def test_single_null_sku_id_never_becomes_assignable_string_none(self):
        product={'identityJson':{'modelCode':'NA-H74'},'skus':[
            {'skuId':None,'skuName':'without box','skuImageUrl':'https://x/old'}]}
        images=[{'url':'https://x/body','model':'NA-H74','verified':True,'clean':True,
                 'image_type':'FIGURE','sha256':'a'*64,'evidence_ids':['SKU_OBS']}]
        result=plan_assignments(product,images)
        self.assertFalse(result['assignments'])
        self.assertTrue(result['deferred'])
        self.assertEqual(result['deferred_reasons']['None'],'SKU_IDENTIFIER_UNVERIFIED')

    def test_standard_cli_missing_ids_defer_distinct_original_rows_without_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            writer,path,_,error=cli.AccountCliTests().execute(temp,case='sku_missing_ids')
            self.assertIsNone(error,repr(error))
            self.assertEqual((writer.saves,writer.uploads),(0,0))
            candidates=json.loads((path/'semantic_validation.json').read_text(encoding='utf-8'))['candidates']
            deferred=[r for r in candidates if r['remedy_id'].startswith('SKU_DEFER_')]
            self.assertEqual(len(deferred),2)
            self.assertEqual(len({r['remedy_id'] for r in deferred}),2)
            self.assertEqual({r['target']['sku_row_index'] for r in deferred},{0,1})
            self.assertTrue(all('SKU_IDENTIFIER_UNVERIFIED' in r['reason_codes'] for r in deferred))
