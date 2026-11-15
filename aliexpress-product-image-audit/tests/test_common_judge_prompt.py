from model_budget_fixtures import authorize_http_fake,request_with_fake_budget
import json
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from ai_judge import JudgeClient
from ai_judge.cache import cache_key
from budget_manager import BudgetManager


class CommonPromptTests(unittest.TestCase):
    def test_common_types_and_bindings_are_sent(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{}'
        with tempfile.TemporaryDirectory() as root:
            client = JudgeClient(BudgetManager({'ai_requests': 1}), root)
            with patch.dict('os.environ', {'VLM_API_KEY': 'test-placeholder'}), patch('ai_judge.client._open_model_request', return_value=response) as request:
                request_with_fake_budget(client,'test', {'task_type': 'title_semantics', 'id': 'A', 'evidence_ids': ['E']}, {})
            prompt = json.loads(request.call_args.args[0].data)['messages'][0]['content'][0]['text']
        for text in ('confidence must be a JSON number from 0 to 1, not a string or percentage',
                     'abstain must be a JSON boolean', 'evidence_ids must be a non-empty array',
                     'only IDs from the supplied item.evidence_ids', 'task_type must exactly equal',
                     'item_id must exactly equal', 'decision must be one of MATCH, MISMATCH, UNCERTAIN'):
            self.assertIn(text, prompt)

    def test_common_contract_changes_cache_key(self):
        from ai_judge import client
        before = cache_key('title_semantics', {}, {}, 'test')
        with patch.object(client, 'COMMON_OUTPUT_CONTRACT', client.COMMON_OUTPUT_CONTRACT + ' changed'):
            self.assertNotEqual(before, cache_key('title_semantics', {}, {}, 'test'))
