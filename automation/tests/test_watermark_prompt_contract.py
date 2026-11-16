from model_budget_fixtures import authorize_http_fake,request_with_fake_budget
import json
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from mye_c_automation.ai_judge import JudgeClient
from mye_c_automation.ai_judge.cache import cache_key
from mye_c_automation.ai_judge import watermark
from mye_c_automation.budget_manager import BudgetManager


class WatermarkPromptTests(unittest.TestCase):
    def test_sent_prompt_has_one_explicit_watermark_contract(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{}'
        with tempfile.TemporaryDirectory() as root:
            client = JudgeClient(BudgetManager({'ai_requests': 1}), root)
            with patch.dict('os.environ', {'VLM_API_KEY': 'test-only-placeholder'}), \
                    patch('mye_c_automation.ai_judge.client._open_model_request', return_value=response) as request:
                request_with_fake_budget(client,'test', {'task_type': 'watermark', 'id': 'A'}, {})
            body = json.loads(request.call_args.args[0].data)
        prompt = body['messages'][0]['content'][0]['text']
        self.assertIn('Required top-level fields: schema_version, task_type, item_id, confidence, abstain, image_size', prompt)
        self.assertIn('owner and location are non-empty strings', prompt)
        self.assertIn('Do not return decision', prompt)
        self.assertIn('classification=unknown and abstain=true on THAT mark', prompt)
        self.assertNotIn('or decision MATCH/MISMATCH/UNCERTAIN', prompt)
        for field in ('coverage_complete','no_marks_detected','bbox_xyxy','unresolved_items','watermark/v3'):self.assertIn(field,prompt)

    def test_cache_key_includes_task_prompt(self):
        before = cache_key('watermark', {}, {}, 'test')
        with patch.object(watermark, 'PROMPT', watermark.PROMPT + ' changed'):
            self.assertNotEqual(before, cache_key('watermark', {}, {}, 'test'))
