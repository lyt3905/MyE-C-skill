"""Real CLI and audit/compiler; fake external judgements and remote transport."""
import json
import tempfile
import unittest
import test_v13_account_cli


class SemanticCliTests(unittest.TestCase):
    def test_sop_alias_small_scale_is_preserved_through_standard_cli(self):
        with tempfile.TemporaryDirectory() as root:
            writer,path,_,error=self.execute(root,'title_small_scale')
            self.assertIsNone(error,repr(error))
            self.assertEqual((writer.uploads,writer.saves,writer.translations),(0,1,1))
            after=writer.product(1);before=self.read(path,'audit_product.json')
            self.assertIn('Small Scale',after['titleEn'])
            for field in ('descriptionJson','images','skus','price','weight','status'):
                self.assertEqual(after[field],before[field])
            self.assertEqual(self.read(path,'state.json')['state'],'AUTO_VERIFIED')
    def execute(self,root,case):
        return test_v13_account_cli.AccountCliTests().execute(root,case=case)

    def read(self,path,name):return json.loads((path/name).read_text(encoding='utf-8'))

    def test_title_cli_saves_once_then_translates_and_verifies_opaque_fields(self):
        with tempfile.TemporaryDirectory() as root:
            writer,path,_,error=self.execute(root,'title')
            self.assertIsNone(error,repr(error))
            self.assertEqual((writer.uploads,writer.saves,writer.translations),(0,1,1))
            after=writer.product(1);before=self.read(path,'audit_product.json')
            self.assertIn('Megatank',after['titleEn'])
            self.assertEqual(after['titleTranslationZh'],'热销 NA-H74 威震天')
            for field in ('descriptionJson','price','weight','status','images'):
                self.assertEqual(after[field],before[field])
            self.assertEqual(self.read(path,'state.json')['state'],'AUTO_VERIFIED')
            self.assertEqual(self.read(path,'dry_run.json')['planned_upload_count'],0)

    def test_sku_cli_reassigns_without_box_and_preserves_with_box_reference(self):
        with tempfile.TemporaryDirectory() as root:
            writer,path,_,error=self.execute(root,'sku')
            self.assertIsNone(error,repr(error))
            self.assertEqual((writer.uploads,writer.saves,writer.translations),(0,1,0))
            after=writer.product(1)
            self.assertEqual([s['skuImageUrl'] for s in after['skus']],['https://fake/detail','https://fake/main'])
            self.assertEqual(after['images']['sku'],['https://fake/main','https://fake/detail'])
            self.assertEqual(self.read(path,'state.json')['state'],'AUTO_VERIFIED')
            self.assertEqual(after['descriptionJson'],'opaque invalid JSON { https://fake/main')

    def test_cli_identity_packaging_uncertainties_do_not_write(self):
        for case in ('title_conflict','sku_color_conflict','sku_missing_ids'):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as root:
                writer,path,_,error=self.execute(root,case)
                self.assertIsNone(error,repr(error))
                self.assertEqual((writer.uploads,writer.saves,writer.translations),(0,0,0))
                self.assertEqual(self.read(path,'state.json')['state'],'DEFERRED')

    def test_missing_template_is_deferred_without_internal_evidence_hash_failure(self):
        import hashlib
        with tempfile.TemporaryDirectory() as root:
            writer,path,_,error=self.execute(root,'missing_template')
            self.assertIsNone(error,repr(error))
            self.assertEqual(self.read(path,'state.json')['state'],'DEFERRED')
            flags=self.read(path,'audit_flags.json')
            self.assertIn('REQUIRED_TEMPLATES_NOT_CONFIGURED',[a['type'] for a in flags['anomalies']])
            manifest=self.read(path,'evidence_manifest.json')
            expected=next(r['sha256'] for r in manifest['files'] if r['path']=='audit_flags.json')
            self.assertEqual(expected,hashlib.sha256((path/'audit_flags.json').read_bytes()).hexdigest())
            self.assertEqual((writer.uploads,writer.saves),(0,0))
