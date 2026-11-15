import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from auto_workflow import prepare
from job_manager import atomic_json


class DeferralDiagnosticsTests(unittest.TestCase):
    def prepare_item(self, judgement, reference_only=False, expect_plan=False, allowed_actions=()):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            item = dict(id='WM_MAIN_000', task_type='watermark', pool='main', index=0,
                        image_id='MAIN_000', local=str(root/'source.png'), reference_only=reference_only, evidence_ids=['WM_MAIN_000'])
            for name, value in {
                'audit_product.json': {'images': {'main': ['https://x/a']}, 'skus': []},
                'ai_queue.json': {'items': [item]},
                'ai_judgements.json': {'WM_MAIN_000': judgement},
                'audit_raw.json': {'images': []},
                'audit_flags.json': {'summary': {'ocr_enabled': True}},
            }.items():
                atomic_json(root / name, value)
            class Policy:
                config = {}
                sha256 = 'a' * 64
                def permits(self, action): return action in allowed_actions
            with patch('auto_workflow.RemedyPlanner') as planner, \
                 patch('semantic_remedies.build', return_value=([], set(), set())), \
                 patch('audit_coverage.verify_sources', return_value={'ok': True, 'missing_urls': [], 'errors': []}), \
                 patch('auto_workflow.compile_auto_plan', side_effect=lambda root, job, rows, policy: rows):
                planner.return_value.plan.return_value=None
                planner.return_value.quality_gate.inspector.propose.return_value={}
                rows = prepare(root, {'shop_id': 7}, Policy())
                if expect_plan:planner.return_value.plan.assert_called_once()
                else:planner.return_value.plan.assert_not_called()
                self.last_geometry_calls=planner.return_value.quality_gate.inspector.propose.call_count
                return rows

    def test_low_confidence_factory_is_not_reported_as_failed_remediation(self):
        rows = self.prepare_item({'status': 'REVIEW', 'results': [
            {'classification': 'official_marketing_text', 'confidence': .72, 'abstain': False}] * 2})
        self.assertEqual(rows[0]['reason_codes'], ['WATERMARK_OWNERSHIP_UNVERIFIED', 'MODEL_CONFIDENCE_BELOW_THRESHOLD'])
        self.assertNotIn('NO_VERIFIED_REMEDY', rows[0]['reason_codes'])

    def test_missing_model_results_are_explicit(self):
        rows = self.prepare_item({})
        self.assertIn('MODEL_RESULTS_MISSING', rows[0]['reason_codes'])

    def test_unverified_reference_does_not_hide_classification_blocker(self):
        rows = self.prepare_item({'status': 'REVIEW', 'results': [
            {'classification': 'manufacturer_branding', 'confidence': .6, 'abstain': True}]}, True)
        self.assertIn('MODEL_ABSTAINED', rows[0]['reason_codes'])
        self.assertIn('SKU_REFERENCE_ONLY_NO_POOL_TARGET', rows[0]['reason_codes'])

    def test_high_confidence_factory_still_keeps_without_remediation(self):
        rows = self.prepare_item({'status': 'CLEAN', 'results': [
            {'task_type': 'watermark', 'classification': 'official_marketing_text', 'confidence': .99}] * 2})
        self.assertEqual(rows, [])

    def test_disabled_geometry_actions_do_not_spend_on_model_proposals(self):
        self.prepare_item({'status':'HIT','results':[
            {'task_type':'watermark','classification':'third_party_store_logo','confidence':.99}]*2},expect_plan=True)
        self.assertEqual(self.last_geometry_calls,0)

    def test_allowed_crop_still_requests_geometry(self):
        self.prepare_item({'status':'HIT','results':[
            {'task_type':'watermark','classification':'third_party_store_logo','confidence':.99}]*2},
            expect_plan=True,allowed_actions=('CROP_BANNER',))
        self.assertEqual(self.last_geometry_calls,1)

    def test_missing_sku_ids_stop_before_spending_on_visual_assignment(self):
        from semantic_remedies import build
        class Inspector:
            calls = 0
            def observe_image(self, path, product):
                self.calls += 1
                return {}
        inspector = Inspector()
        product = {'skus': [
            {'id': None, 'skuName': 'no retail box'},
            {'id': None, 'skuName': 'with retail box'}]}
        rows, _, _ = build(product, {}, [], [
            {'file': 'unused.png', 'url': 'https://x/a'}], inspector, 7)
        self.assertEqual(inspector.calls, 0)
        self.assertEqual(len(rows), 2)
        self.assertEqual({row['target']['sku_row_index'] for row in rows}, {0, 1})
        self.assertTrue(all(row['reason_codes'] == ['SKU_IDENTIFIER_UNVERIFIED'] for row in rows))
