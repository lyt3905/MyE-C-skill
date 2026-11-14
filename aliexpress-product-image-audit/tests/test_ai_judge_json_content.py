from watermark_fixtures import exhaustive
import json
import tempfile
import unittest

from ai_judge import JudgeClient
from budget_manager import BudgetManager


class JsonContentTests(unittest.TestCase):
    def setUp(self):
        self.result = dict(task_type='watermark', item_id='A', classification='marketing_text',
                           owner='store', location='center', confidence=.95,
                           abstain=False, evidence_ids=['A'])

        self.result=exhaustive(self.result)

    def classify(self, content):
        with tempfile.TemporaryDirectory() as root:
            client = JudgeClient(BudgetManager({'ai_requests': 10}), root,
                                 models=('test',), retries=0,
                                 transport=lambda *args: {'choices': [{'message': {'content': content}}]})
            return client.classify('watermark', {'id': 'A', 'evidence_ids': ['A'], 'dimensions':[800,800]}, {})

    def test_plain_and_complete_single_fences(self):
        raw = json.dumps(self.result)
        for content in (raw, '```json\n' + raw + '\n```', '```\n' + raw + '\n```',
                        ' \n```json\r\n' + raw + '\r\n```\n '):
            with self.subTest(content=content):
                output = self.classify(content)
                self.assertEqual(output['status'], 'REVIEW')  # marketing_text requires review under existing policy.
                self.assertEqual(output['results'], [self.result])

    def test_mixed_or_incomplete_content_rejected(self):
        raw = json.dumps(self.result)
        for content in ('Explanation ' + raw, raw + ' trailing',
                        'Before\n```json\n' + raw + '\n```',
                        '```json\n' + raw, raw + '\n```',
                        '```json\n' + raw + '\n```\nafter',
                        '```json\n' + raw + '\n```\n```json\n{}\n```'):
            with self.subTest(content=content):
                self.assertEqual(self.classify(content)['status'], 'NEEDS_REVIEW')

    def test_fence_does_not_relax_schema(self):
        for invalid in ({}, dict(self.result, confidence=True), dict(self.result, evidence_ids=['other'])):
            with self.subTest(invalid=invalid):
                self.assertEqual(self.classify('```json\n' + json.dumps(invalid) + '\n```')['status'],
                                 'NEEDS_REVIEW')
