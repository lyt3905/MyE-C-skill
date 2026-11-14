import json
import tempfile
import unittest
from pathlib import Path

from ai_judge import JudgeClient
from budget_manager import BudgetManager
import test_v13_account_cli as cli


class StorePolicyConsensusCliTests(unittest.TestCase):
    def run_case(self, root, conflict):
        budget = BudgetManager({'ai_requests': 4, 'full_resolution_images': 4})
        def transport(model, item, context):
            row = dict(task_type='watermark', item_id=item['id'],
                       classification='third_party_store_banner' if model == 'fake-a' else 'third_party_store_logo',
                       owner='Different Store' if conflict and model == 'fake-b' else 'Known Toy Store',
                       location='bottom banner', confidence=.99, abstain=False, evidence_ids=item['evidence_ids'])
            return {'choices': [{'message': {'content': json.dumps(row)}}]}
        judge = JudgeClient(budget, Path(root) / 'fake-judge-cache', models=('fake-a', 'fake-b'),
                            retries=0, transport=transport)
        try:
            return cli.AccountCliTests().execute(root, queue_judge=judge)
        finally:
            budget.close()

    def test_same_store_subtypes_pass_through_independent_quality_to_fake_writer(self):
        with tempfile.TemporaryDirectory() as root:
            writer, path, _, error = self.run_case(root, False)
            self.assertIsNone(error, repr(error))
            self.assertEqual((writer.uploads, writer.saves), (1, 1))
            judgements = json.loads((path / 'ai_judgements.json').read_text())
            self.assertTrue(any(x['status'] == 'HIT' for x in judgements.values()))
            self.assertTrue(json.loads((path / 'candidate_quality.json').read_text())['items'][0]['ok'])
            self.assertTrue(json.loads((path / 'content_validation.json').read_text())['ok'])

    def test_different_store_owners_block_before_any_fake_write(self):
        with tempfile.TemporaryDirectory() as root:
            writer, path, _, error = self.run_case(root, True)
            self.assertIsNone(error, repr(error))
            self.assertEqual((writer.uploads, writer.saves), (0, 0))
            self.assertEqual(json.loads((path / 'state.json').read_text())['state'], 'DEFERRED')
