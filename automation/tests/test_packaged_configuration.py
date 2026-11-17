"""The independent software ships schemas agreeing with its existing validators."""
import json
import tempfile
import unittest
from pathlib import Path
from jsonschema import Draft202012Validator
from mye_c_automation.resources import resource_path

class PackagedConfigurationTests(unittest.TestCase):
    def test_all_authorization_examples_validate_and_writes_default_disabled(self):
        schema=json.loads(resource_path('config/schemas/automation.v1.schema.json').read_text())
        validator=Draft202012Validator(schema)
        for path in resource_path('config').glob('automation.*.example.json'):
            config=json.loads(path.read_text())
            self.assertEqual(list(validator.iter_errors(config)),[],path.name)
            self.assertFalse(config['enabled'])

    def test_gateway_profiles_and_image_options_have_packaged_schemas(self):
        from mye_c_automation.resources import validate_resource_json
        for path in resource_path('config').glob('model.gateway*.example.json'):
            validate_resource_json(json.loads(path.read_text()),'model-gateway.v1.schema.json')
        validate_resource_json(json.loads(resource_path('config/image-options.v2.example.json').read_text()),'image-options.v2.schema.json')

    def test_file_loaders_and_job_freeze_apply_resource_schemas(self):
        from unittest.mock import patch
        from mye_c_automation.automation_policy import AutomationPolicy
        from mye_c_automation.model_config import load_config
        from mye_c_automation.job_manager import JobManager
        from mye_c_automation.resources import validate_resource_json
        with patch('mye_c_automation.resources.validate_resource_json',wraps=validate_resource_json) as validate,tempfile.TemporaryDirectory() as root:
            AutomationPolicy.load(resource_path('config/automation.v2.example.json'))
            load_config(resource_path('config/model.gateway8788.example.json'))
            JobManager(Path(root)/'jobs').create(1,7,{},image_workflow='v2')
            self.assertEqual({call.args[1] for call in validate.call_args_list},{'automation.v1.schema.json','model-gateway.v1.schema.json','image-options.v2.schema.json'})
