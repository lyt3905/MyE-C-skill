import json,tempfile,unittest
from pathlib import Path
from jsonschema import Draft202012Validator
from automation_policy import AutomationPolicy
from test_auto_decision import CONFIG
from job_manager import JobManager
import test_auto_workflow_more as helpers

class SchemaContractTests(unittest.TestCase):
    def schema(self,name):return json.loads((Path(__file__).resolve().parents[1]/'scripts'/'config'/'schemas'/name).read_text(encoding='utf-8'))
    def test_automation_example_and_rejection_agree(self):
        schema=self.schema('automation.v1.schema.json');Draft202012Validator.check_schema(schema)
        validator=Draft202012Validator(schema)
        self.assertEqual(list(validator.iter_errors(CONFIG)),[])
        for changes in ({'max_site_save_per_job':2},{'preserve_product_status':False},{'unexpected_field':True}):
            config=dict(CONFIG,**changes)
            self.assertTrue(list(validator.iter_errors(config)))
            with self.assertRaises(ValueError):AutomationPolicy(config)
    def test_actual_workflow_plan_and_candidates_validate(self):
        plan_schema=self.schema('plan.v3.schema.json');remedy_schema=self.schema('remedy-candidate.v1.schema.json')
        Draft202012Validator.check_schema(plan_schema);Draft202012Validator.check_schema(remedy_schema)
        with tempfile.TemporaryDirectory() as root:
            result,writer,product=helpers.AdditionalWorkflowTests().execute_case(root,crop=True)
            path=next(Path(root).glob('JOB_*'))
            plan=json.loads((path/'plan.v2.json').read_text(encoding='utf-8'))
            self.assertEqual(list(Draft202012Validator(plan_schema).iter_errors(plan)),[])
            for row in json.loads((path/'remedy_candidates.json').read_text(encoding='utf-8'))['items']:
                self.assertEqual(list(Draft202012Validator(remedy_schema).iter_errors(row)),[])
