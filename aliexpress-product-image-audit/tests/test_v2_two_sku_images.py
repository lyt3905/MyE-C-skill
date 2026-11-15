"""Two no-box photos may illustrate the existing boxed/unboxed variants."""
import copy
import json
import tempfile
import unittest
import test_v2_repairs_sku as fixtures
import test_v2_workflow as workflow


class TwoSkuImagesTests(unittest.TestCase):
    def product(self):
        return dict(skus=[dict(skuId='without',skuName='no retail box',originalBox=False,price=12,skuImageUrl='https://fake/0'),
                          dict(skuId='with',skuName='with retail box',originalBox=True,price=20,skuImageUrl='https://fake/0')])

    def test_two_distinct_photos_bound_to_two_existing_skus(self):
        from sku_assignment import select_v2
        product=self.product();before=copy.deepcopy(product)
        result=select_v2(product,fixtures.RepairSkuTests().records())
        self.assertEqual(result['assignments'],{'without':'https://fake/0','with':'https://fake/2'})
        self.assertFalse(result['reason_codes'])
        self.assertTrue(result['capability_evidence']['second_reference_assigned'])
        selected=result['selected_sku_images']
        self.assertEqual([r['target_sku_id'] for r in selected],['without','with'])
        self.assertEqual([r['logical_sku_group'] for r in selected],['WITHOUT_RETAIL_BOX','WITH_RETAIL_BOX'])
        self.assertTrue(all(r['source_retail_box_status']=='ABSENT' for r in selected))
        self.assertFalse(result['site_multi_image_supported'])
        self.assertEqual(product,before)

    def test_variant_order_does_not_decide_packaging(self):
        from sku_assignment import select_v2
        product=self.product();product['skus'].reverse()
        result=select_v2(product,fixtures.RepairSkuTests().records())
        self.assertEqual(result['assignments'],{'without':'https://fake/0','with':'https://fake/2'})

    def test_existing_distinct_correct_references_are_preserved(self):
        from sku_assignment import select_v2
        product=self.product()
        product['skus'][0]['skuImageUrl']='https://fake/2'
        result=select_v2(product,fixtures.RepairSkuTests().records())
        self.assertEqual(result['assignments'],{'without':'https://fake/2','with':'https://fake/0'})
        self.assertFalse(result['reason_codes'])

    def test_no_id_rows_require_opt_in_and_bind_both_hashes(self):
        from sku_assignment import select_v2
        from snapshot_sku import row_hash
        product=self.product()
        for row in product['skus']:row.pop('skuId')
        records=fixtures.RepairSkuTests().records()
        self.assertFalse(select_v2(product,records)['row_assignments'])
        result=select_v2(product,records,allow_snapshot_rows=True)
        self.assertEqual(result['row_assignments'],[dict(index=n,source_sha256=row_hash(product['skus'][n]),url=url) for n,url in enumerate(('https://fake/0','https://fake/2'))])
        self.assertFalse(result['reason_codes'])
        self.assertEqual([r['target_sku_locator']['index'] for r in result['selected_sku_images']],[0,1])

    def test_shortage_does_not_duplicate_photo_into_second_variant(self):
        from sku_assignment import select_v2
        result=select_v2(self.product(),fixtures.RepairSkuTests().records()[:1])
        self.assertEqual(result['assignments'],{'without':'https://fake/0'})
        self.assertIn('SKU_IMAGE_SHORTAGE=1_OF_2',result['reason_codes'])
        self.assertFalse(result['capability_evidence']['second_reference_assigned'])

    def test_fake_two_variant_save_and_readback_with_ids_or_row_hashes(self):
        for missing in (False,True):
            with self.subTest(missing_id=missing),tempfile.TemporaryDirectory() as root:
                s=workflow.V2WorkflowTests.scenario(self,root,['KEEP','KEEP'],two_sku_rows=True,missing_sku_id=missing,snapshot_sku_rows=missing)
                self.assertEqual(s['writer'].saves,1)
                self.assertEqual(s['writer'].uploads,0)
                self.assertTrue(s['result']['content_validation']['ok'])
                self.assertEqual(s['result']['status'],'AUTO_VERIFIED')
                skus=s['product']['skus']
                self.assertNotEqual(skus[0]['skuImageUrl'],skus[1]['skuImageUrl'])
                for n,row in enumerate(skus):
                    self.assertEqual({k:v for k,v in row.items() if k!='skuImageUrl'}, {k:v for k,v in s['original']['skus'][n].items() if k!='skuImageUrl'})
                    self.assertIn(row['skuImageUrl'],s['product']['images']['sku'])
                selection=json.loads((s['root']/'v2_sku_selection.json').read_text())
                self.assertFalse(selection['reason_codes'])
                self.assertEqual(s['product']['descriptionJson'],s['original']['descriptionJson'])

    def test_repaired_candidate_urls_are_resolved_for_both_variants(self):
        for missing in (False,True):
            with self.subTest(missing_id=missing),tempfile.TemporaryDirectory() as root:
                s=workflow.V2WorkflowTests.scenario(self,root,['REMOVE_TEXT','REMOVE_TEXT'],two_sku_rows=True,sku_on_first=True,missing_sku_id=missing,snapshot_sku_rows=missing)
                self.assertEqual(s['writer'].uploads,2)
                self.assertEqual(s['writer'].saves,1)
                urls={r['skuImageUrl'] for r in s['product']['skus']}
                self.assertEqual(urls,{'https://fake/upload1','https://fake/upload2'})
                self.assertTrue(s['result']['content_validation']['ok'])


if __name__=='__main__':unittest.main()
