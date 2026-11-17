import json
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from mye_c_automation import workflow_runner
import test_v13_account_cli


class MainCleanupCliTests(unittest.TestCase):
    def read(self,path,name):return json.loads((path/name).read_text(encoding='utf-8'))

    def test_seven_main_images_global_plan_removes_only_proven_duplicate(self):
        with tempfile.TemporaryDirectory() as root:
            writer,path,_,error=test_v13_account_cli.AccountCliTests().execute(root,case='cleanup_safe')
            self.assertIsNone(error,repr(error))
            self.assertEqual((writer.uploads,writer.saves),(0,1))
            self.assertEqual(writer.product(1)['images']['main'],['https://fake/main_'+str(i) for i in range(6)])
            cleanup=self.read(path,'main_cleanup.json')
            self.assertEqual(cleanup['selected_delete_indices'],[6])
            self.assertEqual(cleanup['retained_main_indices'],[0,1,2,3,4,5])
            self.assertEqual(self.read(path,'state.json')['state'],'AUTO_VERIFIED')
            self.assertIn('main_cleanup.json',{r['path'] for r in self.read(path,'plan.v2.json')['evidence_refs']})
            self.assertEqual(writer.product(1)['descriptionJson'],'opaque invalid JSON { https://fake/main')

    def test_keep_sku_referenced_copy_and_reindex_main_without_changing_sku_fields(self):
        with tempfile.TemporaryDirectory() as root:
            writer,path,_,error=test_v13_account_cli.AccountCliTests().execute(root,case='cleanup_sku_reference')
            self.assertIsNone(error,repr(error))
            self.assertEqual((writer.uploads,writer.saves),(0,1))
            self.assertEqual(self.read(path,'main_cleanup.json')['selected_delete_indices'],[0])
            after=writer.product(1)
            self.assertEqual(after['images']['main'],['https://fake/main_'+str(i) for i in range(1,6)]+['https://fake/copy'])
            self.assertEqual(after['skus'][0],{'skuId':1,'skuName':'without box','skuImageUrl':'https://fake/copy','price':10})
            self.assertEqual(after['images']['sku'],['https://fake/copy'])

    def test_protected_content_disagreement_near_hash_or_insufficient_global_evidence_never_deletes(self):
        for case in ('cleanup_box','cleanup_official','cleanup_disagreement','cleanup_phash_only','cleanup_insufficient'):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as root:
                writer,path,_,error=test_v13_account_cli.AccountCliTests().execute(root,case=case)
                self.assertIsNone(error,repr(error))
                self.assertEqual((writer.uploads,writer.saves),(0,0))
                self.assertEqual(self.read(path,'state.json')['state'],'DEFERRED')
                self.assertEqual(self.read(path,'main_cleanup.json')['selected_delete_indices'],[])

    def test_previewed_global_plan_tamper_blocks_before_any_write(self):
        def tamper(writer,path):
            target=path/'main_cleanup.json';target.write_bytes(target.read_bytes()+b' ')
        with tempfile.TemporaryDirectory() as root:
            writer,_,_,error=test_v13_account_cli.AccountCliTests().execute(root,case='cleanup_safe',after_preview=tamper)
            self.assertIsNotNone(error)
            self.assertEqual((writer.uploads,writer.saves),(0,0))

    def test_changed_retained_reference_bytes_cannot_be_verified_or_resaved(self):
        def mutate(writer,path):writer.image_bytes['https://fake/main_0']=writer.image_bytes['https://fake/detail']
        with tempfile.TemporaryDirectory() as root:
            writer,path,_,error=test_v13_account_cli.AccountCliTests().execute(root,case='cleanup_safe',after_preview=mutate)
            self.assertIsNone(error,repr(error))
            self.assertEqual((writer.uploads,writer.saves),(0,1))
            self.assertEqual(self.read(path,'state.json')['state'],'CONTENT_REVIEW_REQUIRED')

    def test_rollback_cli_refuses_reintroducing_seven_main_images_without_writing(self):
        with tempfile.TemporaryDirectory() as root:
            writer,path,_,error=test_v13_account_cli.AccountCliTests().execute(root,case='cleanup_safe')
            self.assertIsNone(error,repr(error))
            args=['mye_c_automation.workflow_runner.py','rollback-preview','--job',path.name,'--site-config',str(Path(root)/'site.json'),'--root',str(path.parent)]
            with patch('sys.argv',args),patch('mye_c_automation.site_client._SiteTransport',return_value=writer),contextlib.redirect_stdout(io.StringIO()),self.assertRaisesRegex(ValueError,'ROLLBACK_TARGET_INVALID'):
                workflow_runner.main()
            self.assertEqual((writer.uploads,writer.saves),(0,1))
            self.assertEqual(len(writer.product(1)['images']['main']),6)
