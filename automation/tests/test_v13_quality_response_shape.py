import copy
import json
import tempfile
import unittest

from mye_c_automation.ai_judge import JudgeClient
from mye_c_automation.ai_judge.schemas import validate_result
from mye_c_automation.budget_manager import BudgetManager


FLAGS = ('product_identity_match', 'source_clean', 'candidate_visual_validation',
         'protected_elements_preserved', 'residual_pass', 'subject_bounds_safe',
         'model_match', 'packaging_match', 'official_source')


class QualityResponseShapeTests(unittest.TestCase):
    def row(self):
        # Shape and negative checks from the captured real GLM response.
        return dict(task_type='remedy_quality', item_id='Q', decision='MISMATCH',
                    confidence=.95, abstain=False, evidence_ids=['Q'],
                    **dict(zip(FLAGS, (True, True, False, True, False, True, True, False, True))))

    def test_flat_quality_fields_preserve_negative_decision_and_false_flags(self):
        row = self.row()
        original = copy.deepcopy(row)
        result = validate_result(row, 'remedy_quality', 'Q', {'evidence_ids': ['Q']})
        self.assertEqual(row, original)
        self.assertEqual(result['decision'], 'MISMATCH')
        self.assertEqual(result['checks'], {k: original[k] for k in FLAGS})
        self.assertFalse(result['checks']['candidate_visual_validation'])
        self.assertFalse(result['checks']['packaging_match'])
        self.assertTrue(set(FLAGS).isdisjoint(result))

    def test_flat_contract_does_not_invent_or_coerce_required_checks(self):
        missing = self.row(); del missing['residual_pass']
        string = self.row(); string['residual_pass'] = 'false'
        number = self.row(); number['source_clean'] = 1
        conflict = self.row(); conflict['checks'] = {k: True for k in FLAGS}
        null = self.row(); null['checks'] = None
        for row in (missing, string, number, conflict, null):
            with self.subTest(row=row), self.assertRaises(ValueError):
                validate_result(row, 'remedy_quality', 'Q', {'evidence_ids': ['Q']})

    def test_identity_and_evidence_checks_still_apply(self):
        for changes in ({'item_id': 'OTHER'}, {'evidence_ids': ['OTHER']},
                        {'confidence': True}, {'decision': 'PASS'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_result(dict(self.row(), **changes), 'remedy_quality', 'Q', {'evidence_ids': ['Q']})

    def test_client_keeps_mismatch_and_canonical_cache_without_retry(self):
        calls = []
        def transport(*args):
            calls.append(args[0])
            return {'choices': [{'message': {'content': json.dumps(self.row())}}]}
        with tempfile.TemporaryDirectory() as root:
            budget = BudgetManager({'ai_requests': 2})
            client = JudgeClient(budget, root, models=('fake-a', 'fake-b'), retries=0, transport=transport)
            try:
                item = {'id': 'Q', 'evidence_ids': ['Q']}
                first = client.classify('remedy_quality', item, {})
                self.assertEqual(first['status'], 'HIT')
                self.assertEqual([r['decision'] for r in first['results']], ['MISMATCH', 'MISMATCH'])
                self.assertTrue(all(r['checks']['residual_pass'] is False for r in first['results']))
                second = client.classify('remedy_quality', item, {})
                self.assertEqual(first, second)
                self.assertEqual(calls, ['fake-a', 'fake-b'])
            finally:
                budget.close()
