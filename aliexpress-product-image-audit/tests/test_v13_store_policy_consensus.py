import json
import tempfile
import unittest

from ai_judge import JudgeClient
from budget_manager import BudgetManager
from policy_engine import evaluate


class StorePolicyConsensusTests(unittest.TestCase):
    def classify(self, first='third_party_store_banner', second='third_party_store_logo',
                 owners=('Known Toy Store', 'Known Toy Store'), confidence=.95, abstain=False):
        responses = []
        for category, owner in zip((first, second), owners):
            responses.append(dict(task_type='watermark', item_id='Q23', classification=category,
                                  owner=owner, location='bottom banner', confidence=confidence,
                                  abstain=abstain, evidence_ids=['Q23']))
        with tempfile.TemporaryDirectory() as root:
            budget = BudgetManager({'ai_requests': 2})
            client = JudgeClient(budget, root, models=('fake-a', 'fake-b'), retries=0,
                transport=lambda model, *_: {'choices': [{'message': {'content': json.dumps(
                    responses[0 if model == 'fake-a' else 1])}}]})
            try:
                item = {'id': 'Q23', 'evidence_ids': ['Q23']}
                first_result = client.classify('watermark', item, {})
                cached = client.classify('watermark', item, {})
                self.assertEqual(first_result, cached)
                self.assertEqual(client.metrics['requests'], 2)
                return first_result
            finally:
                budget.close()

    def test_same_specific_store_and_existing_remove_policy_form_candidate(self):
        result = self.classify(owners=(' 新潮模玩汇 ', '新潮模玩汇'))
        self.assertEqual(result['status'], 'HIT')
        self.assertEqual(evaluate(result), 'REMOVE_CANDIDATE')
        self.assertNotIn('authorized_actions', result)

    def test_owner_conflict_or_placeholder_still_defers(self):
        for owners in (('Store A', 'Store B'), ('unknown', 'unknown'), ('store', 'store'),
                       ('seller', 'seller'), ('third_party_store', 'third_party_store'),
                       ('third_party', 'third_party')):
            with self.subTest(owners=owners):
                result = self.classify(owners=owners)
                self.assertEqual(result['status'], 'REVIEW')
                self.assertEqual(evaluate(result), 'NEEDS_REVIEW')

    def test_protected_categories_never_merge_with_store_or_each_other(self):
        for first, second in (('third_party_store_logo', 'social_account_signature'),
                              ('manufacturer_branding', 'product_print')):
            with self.subTest(first=first, second=second):
                self.assertEqual(self.classify(first, second)['status'], 'REVIEW')

    def test_review_policy_low_confidence_and_abstention_stay_deferred(self):
        for kwargs in ({'second': 'marketing_text'}, {'second': 'chinese_promotion_poster'},
                       {'confidence': .89}, {'abstain': True}):
            with self.subTest(kwargs=kwargs):
                self.assertEqual(self.classify(**kwargs)['status'], 'REVIEW')

    def test_consensus_requires_two_distinct_models_and_watermark_tasks(self):
        from ai_judge.client import _same_store_remove_consensus
        rows=[dict(task_type='watermark', classification=category, owner='Known Toy Store',
                   confidence=.95, abstain=False) for category in ('third_party_store_banner', 'third_party_store_logo')]
        self.assertTrue(_same_store_remove_consensus(rows, ('a', 'b')))
        self.assertFalse(_same_store_remove_consensus(rows, ('a', 'a')))
        self.assertFalse(_same_store_remove_consensus(rows, ('a',)))
        rows[1]['task_type']='title_semantics'
        self.assertFalse(_same_store_remove_consensus(rows, ('a', 'b')))
