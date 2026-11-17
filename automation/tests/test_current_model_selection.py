from mye_c_automation.resources import resource_path
import json
import tempfile
import unittest
import urllib.request
from unittest.mock import patch

from mye_c_automation.ai_judge.client import JudgeClient, _open_model_request
from mye_c_automation.budget_manager import BudgetManager
from mye_c_automation.model_config import DEFAULT_MODELS, load_config


class CurrentModelSelectionTests(unittest.TestCase):
    def test_default_and_gateway_profiles_use_deepseek_only(self):
        with tempfile.TemporaryDirectory() as directory:
            budget = BudgetManager({})
            try:
                self.assertEqual(tuple(JudgeClient(budget, directory).models), DEFAULT_MODELS)
            finally:
                budget.close()
        for name, prefix in (('8788', ''), ('8788.mainflow', ''), ('3425', 'workbuddy/')):
            config = load_config(resource_path('config/model.gateway' + name + '.example.json'))
            self.assertEqual(config['models'], [prefix + model for model in DEFAULT_MODELS])

    def test_disabled_model_is_rejected_before_opening_connection(self):
        for model in ('kimi-k3-1', 'kimi3', 'glm-5v-turbo', 'other','mimo-v2.6-pro','workbuddy/mimo-v2.6-pro'):
            request = urllib.request.Request('http://127.0.0.1:8788/v1/chat/completions',
                                             data=json.dumps({'model': model}).encode())
            with patch('mye_c_automation.ai_judge.client.urllib.request.build_opener') as opener:
                with self.assertRaisesRegex(ValueError, 'MODEL_DISABLED_BY_PROJECT_SELECTION'):
                    _open_model_request(request, 1)
                opener.assert_not_called()

    def test_selected_models_reach_dispatch_without_fallback(self):
        for prefix in ('', 'workbuddy/'):
            for model in DEFAULT_MODELS:
                request = urllib.request.Request('http://127.0.0.1:8788/v1/chat/completions',
                                                 data=json.dumps({'model': prefix + model}).encode())
                with patch('mye_c_automation.ai_judge.client.urllib.request.build_opener') as opener:
                    _open_model_request(request, 1)
                    opener.return_value.open.assert_called_once_with(request, timeout=1)
