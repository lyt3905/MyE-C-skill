import copy,json,tempfile,unittest
from test_v2_vision import observation

def profile(limit=3):
    return dict(schema='model-gateway/v1',base_url='http://127.0.0.1:8788/v1',models=['deepseek-v4.1-flash'],
        max_output_tokens=4096,retries=0,timeout=150,vision_retry_limit=limit)

class VisionRetryThreeTests(unittest.TestCase):
    def run_case(self,mode,*,attempts=None):
        from mye_c_automation.ai_judge.client import JudgeClient
        from mye_c_automation.budget_manager import BudgetManager
        item=dict(id='IMG_A',sha256='a'*64,image_type='MAIN',evidence_ids=['SOURCE']);calls=[]
        def response(model,evidence,context):
            calls.append(copy.deepcopy(evidence));row=observation(evidence)
            if mode=='fourth-valid':
                if len(calls)==1:row.pop('evidence_ids')
                elif len(calls)<4:row['regarding']='Unrequested explanation'
            elif mode=='invalid':row.pop('evidence_ids')
            elif mode=='business' or mode=='protected-schema':
                row=observation(evidence,'REMOVE_TEXT',watermarks=[dict(kind='PRODUCT_PRINT',action='REMOVE_TEXT',bbox=[.1,.1,.2,.2],confidence=.9,preserve_overlap_risk='LOW')])
                if mode=='protected-schema':row.pop('evidence_ids')
            elif mode in ('permanent','temporary'):
                import urllib.error
                raise urllib.error.HTTPError('https://fake',401 if mode=='permanent' else 429,'test',{},None)
            return dict(choices=[dict(message=dict(content=json.dumps(row)))],usage=dict(prompt_tokens=1,completion_tokens=1,total_tokens=2))
        with tempfile.TemporaryDirectory() as d:
            budget=BudgetManager(dict(ai_requests=4))
            try:
                client=JudgeClient(budget,d,transport=response,config=profile(),continue_model_errors=True)
                result=client.classify('image_action_decision',item,{},attempts=attempts)
                return result,calls,copy.deepcopy(client.metrics)
            finally:budget.close()

    def test_profile_accepts_zero_through_three_and_rejects_four_bool_negative(self):
        from mye_c_automation.model_config import validate_config
        for n in range(4):self.assertEqual(validate_config(profile(n))['vision_retry_limit'],n)
        for n in [4,-1,True,3.0]:
            with self.subTest(n=n),self.assertRaises(ValueError):validate_config(profile(n))

    def test_third_retry_can_succeed_and_all_previous_raw_responses_are_retained(self):
        result,calls,metrics=self.run_case('fourth-valid')
        self.assertEqual(result['status'],'VALIDATED');self.assertEqual(len(calls),4)
        self.assertEqual([c['attempt'] for c in metrics['calls']],[1,2,3,4])
        self.assertTrue(all('raw_response' in c for c in metrics['calls']))
        self.assertNotIn('evidence_ids',json.loads(metrics['calls'][0]['raw_response']['choices'][0]['message']['content']))
        self.assertEqual(metrics['total_tokens'],8)

    def test_retry_feedback_names_missing_and_extra_fields_without_changing_evidence(self):
        _,calls,_=self.run_case('fourth-valid')
        self.assertIn('evidence_ids',calls[1]['reason']);self.assertIn('SOURCE',calls[1]['reason'])
        self.assertIn('regarding',calls[2]['reason'])
        self.assertTrue(all(c['id']=='IMG_A' and c['sha256']=='a'*64 and c['evidence_ids']==['SOURCE'] for c in calls))

    def test_three_retries_exhaust_at_four_total_and_return_review(self):
        result,calls,metrics=self.run_case('invalid')
        self.assertEqual(len(calls),4);self.assertEqual(result['status'],'NEEDS_REVIEW')
        self.assertEqual(result['failure_code'],'SCHEMA_VALIDATION_FAILED')
        self.assertFalse(metrics['calls'][-1].get('retry_planned',False))

    def test_caller_can_cap_remaining_additional_requests_at_three(self):
        result,calls,_=self.run_case('invalid',attempts=3)
        self.assertEqual(len(calls),3);self.assertEqual(result['status'],'NEEDS_REVIEW')

    def test_business_and_protected_schema_conflicts_never_retry(self):
        for mode in ['business','protected-schema']:
            with self.subTest(mode=mode):
                result,calls,_=self.run_case(mode)
                self.assertEqual(len(calls),1);self.assertEqual(result['status'],'NEEDS_REVIEW')

    def test_permanent_errors_stop_and_temporary_errors_remain_bounded(self):
        for mode,expected in [('permanent',1),('temporary',4)]:
            with self.subTest(mode=mode):
                result,calls,_=self.run_case(mode)
                self.assertEqual(len(calls),expected);self.assertEqual(result['status'],'NEEDS_REVIEW')

    def test_initialized_configuration_has_three_vision_retries(self):
        from mye_c_automation.configuration import initialize_config
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            initialize_config(d)
            self.assertEqual(json.loads((Path(d)/'model.local.json').read_text())['vision_retry_limit'],3)
