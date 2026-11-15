import copy
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from ai_judge import JudgeClient
from ai_judge.identity_contract import aggregate_identity
from ai_judge.watermark_contract import aggregate_watermarks
from budget_manager import BudgetManager
from full_product_audit import _strong
from policy_engine import evaluate
from test_8788_contract import evidence, identity_result, pair, response
from visual_quality import VisualQualityInspector


class Confidence080Tests(unittest.TestCase):
    def test_watermark_region_and_root_boundary(self):
        for confidence, expected in ((.8, 'PASS'), (.7999, 'UNKNOWN')):
            row = response()
            row['confidence'] = confidence
            row['marks'][0]['confidence'] = confidence
            result = aggregate_watermarks(pair(row), evidence())
            self.assertEqual(result['review_status'], expected)

    def test_identity_dimension_and_root_boundary(self):
        for confidence, expected in ((.8, 'PASS'), (.7999, 'UNKNOWN')):
            row = identity_result()
            row['confidence'] = confidence
            for observation in row['observations'].values():
                observation['confidence'] = confidence
            result = aggregate_identity(pair(row), 'DW-ES09T', {'id': 'ID_X', 'evidence_ids': ['ID_X']})
            self.assertEqual(result['verdict'], expected)

    def test_client_policy_and_full_audit_agree_on_boundary(self):
        for confidence, expected in ((.8, True), (.7999, False)):
            with tempfile.TemporaryDirectory() as directory:
                budget = BudgetManager({'ai_requests': 2})
                def transport(model, item, context):
                    row = dict(task_type='title_semantics', item_id=item['id'], decision='MATCH',
                               confidence=confidence, abstain=False, evidence_ids=item['evidence_ids'])
                    return {'choices': [{'message': {'content': json.dumps(row)}}]}
                try:
                    result = JudgeClient(budget, directory, models=('legacy-a','legacy-b'), transport=transport).classify(
                        'title_semantics', {'id': 'T', 'evidence_ids': ['T']}, {})
                    self.assertEqual(result['status'] == 'CLEAN', expected)
                    self.assertEqual(evaluate(result) == 'KEEP', expected)
                    self.assertEqual(_strong(result), expected)
                finally:
                    budget.close()

    def test_candidate_and_deletion_quality_use_same_boundary(self):
        checks = ('product_identity_match', 'source_clean', 'candidate_visual_validation',
                  'protected_elements_preserved', 'residual_pass', 'subject_bounds_safe',
                  'model_match', 'packaging_match', 'official_source')
        for confidence, expected in ((.8, True), (.7999, False)):
            class Judge:
                def classify(self, task, item, context):
                    row = dict(decision='MATCH', abstain=False, confidence=confidence,
                               checks={key: True for key in checks}, image_type='FIGURE',
                               model='DW-ES09T', color='green', category='DECORATION',
                               is_box=False, is_official=False, information_preserved=True)
                    return {'status': 'CLEAN', 'results': [copy.deepcopy(row), copy.deepcopy(row)]}
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'image.png'
                Image.new('RGB', (800, 800), 'white').save(path)
                inspector = VisualQualityInspector(directory, {'shop_id': 7, 'templates_required': False},
                                                   judge=Judge(), ocr_engine=lambda image: ([], None))
                self.assertEqual(inspector.inspect(path, path, {})['source_clean'], expected)
                self.assertEqual(inspector.inspect_deletion(path, {})['ok'], expected)

    def test_abstention_and_disagreement_still_remain_unresolved(self):
        row = identity_result()
        row['confidence'] = .8
        row['abstain'] = True
        result = aggregate_identity(pair(row), 'DW-ES09T', {'id': 'ID_X', 'evidence_ids': ['ID_X']})
        self.assertEqual(result['verdict'], 'UNKNOWN')
