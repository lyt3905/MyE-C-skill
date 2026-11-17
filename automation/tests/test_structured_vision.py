import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_v2_vision import observation


class StructuredVisionTests(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('mye_c_automation.ai_judge.structured_output'),'Canonical validation adapter missing')
        from mye_c_automation.ai_judge import structured_output
        return structured_output

    def item(self):return dict(id='IMG_A',sha256='a'*64,image_type='MAIN',evidence_ids=['SOURCE'])

    def test_canonical_schema_checked_and_compatible_copy_keeps_semantics(self):
        api=self.api();schema=api.load_v2_schema();before=copy.deepcopy(schema)
        compiled=api.api_compatible_schema(schema)
        self.assertEqual(schema,before);api.assert_schema_equivalent(schema,compiled)
        self.assertTrue({'required','properties','type','enum','additionalProperties','items','minimum','maximum','minItems','maxItems'}<=set(api.schema_keywords(schema)))
        compiled['properties']['decision']['enum'].append('ERASE_ANYTHING')
        with self.assertRaisesRegex(ValueError,'SCHEMA_COMPATIBILITY'):api.assert_schema_equivalent(schema,compiled)

    def test_invalid_schema_and_unsupported_keyword_are_not_silently_weakened(self):
        api=self.api()
        with self.assertRaises(ValueError):api.api_compatible_schema(dict(type='not-a-json-schema-type'))
        with self.assertRaisesRegex(ValueError,'GATEWAY_UNSUPPORTED'):
            api.api_compatible_schema(api.load_v2_schema(),supported_keywords={'type','properties'})

    def test_responses_request_uses_stable_name_none_and_original_without_strict(self):
        api=self.api();chat=dict(model='deepseek-v4.1-flash',max_tokens=4096,messages=[dict(role='user',content=[dict(type='text',text='source data'),dict(type='image_url',image_url=dict(url='data:image/jpeg;base64,AAA',detail='original'))])])
        body=api.responses_request(chat)
        self.assertEqual(body['reasoning'],dict(effort='none'));self.assertEqual(body['max_output_tokens'],4096)
        self.assertEqual(body['text']['format']['type'],'json_schema');self.assertEqual(body['text']['format']['name'],'myec_image_action_decision_v2')
        self.assertNotIn('strict',body['text']['format']);self.assertEqual(body['input'][0]['content'][1]['detail'],'original')
        self.assertEqual(body['input'][0]['content'][1]['image_url'],'data:image/jpeg;base64,AAA')

    def test_responses_status_truncation_empty_and_api_errors_are_distinct(self):
        api=self.api()
        cases=[(dict(status='failed',error=dict(code='bad')), 'API_ERROR'),(dict(status='incomplete',incomplete_details=dict(reason='max_output_tokens')),'MAX_OUTPUT_TOKENS'),(dict(status='incomplete',incomplete_details=dict(reason='content_filter')),'RESPONSE_INCOMPLETE'),(dict(status='in_progress'),'RESPONSE_INCOMPLETE'),(dict(status='completed',output=[]),'EMPTY_OUTPUT')]
        for raw,code in cases:
            with self.subTest(code=code),self.assertRaisesRegex(ValueError,code):api.responses_text(raw)
        raw=dict(status='completed',output=[dict(type='reasoning',content=[dict(type='reasoning_text',text='not the answer')]),dict(type='message',role='assistant',content=[dict(type='output_text',text='{}')])])
        self.assertEqual(api.responses_text(raw),'{}')

    def test_chat_truncation_and_empty_are_not_json_parse_errors(self):
        api=self.api()
        with self.assertRaisesRegex(ValueError,'MAX_OUTPUT_TOKENS'):api.chat_text(dict(choices=[dict(finish_reason='length',message=dict(content='{}'))]))
        with self.assertRaisesRegex(ValueError,'EMPTY_OUTPUT'):api.chat_text(dict(choices=[dict(message=dict(content=''))]))

    def test_json_parser_rejects_non_json_numbers_and_duplicate_business_fields(self):
        from mye_c_automation.ai_judge.client import parse_json_content
        for raw in ['{"confidence":NaN}','{"confidence":Infinity}','{"decision":"REVIEW","decision":"REMOVE_TEXT"}','not json']:
            with self.subTest(raw=raw),self.assertRaises(ValueError):parse_json_content(raw)
        self.assertEqual(parse_json_content('```json\n{"decision":"REVIEW"}\n```'),dict(decision='REVIEW'))

    def test_unverified_or_unsupported_api_is_not_called_schema_enforced(self):
        api=self.api()
        for capability in [None,{},dict(schema_enforced=False)]:
            with self.assertRaisesRegex(ValueError,'GATEWAY_UNSUPPORTED'):api.require_schema_capability(capability)

    def test_temporary_api_retry_is_once_and_unknown_usage_is_not_faked(self):
        import urllib.error
        from mye_c_automation.ai_judge.client import JudgeClient
        from mye_c_automation.budget_manager import BudgetManager
        item=self.item();calls=[]
        config=dict(schema='model-gateway/v1',base_url='http://127.0.0.1:8788/v1',models=['deepseek-v4.1-flash'],max_output_tokens=4096,retries=0,timeout=150,vision_retry_limit=1)
        def response(model,evidence,context):
            calls.append(evidence)
            if len(calls)==1:raise urllib.error.HTTPError('https://fake',429,'temporary',{},None)
            return dict(choices=[dict(message=dict(content=json.dumps(observation(evidence))))],usage=dict(prompt_tokens=1,completion_tokens=1,total_tokens=2))
        with tempfile.TemporaryDirectory() as d:
            budget=BudgetManager(dict(ai_requests=2))
            try:
                client=JudgeClient(budget,d,transport=response,config=config);result=client.classify('image_action_decision',item,{})
                self.assertEqual(result['status'],'VALIDATED');self.assertEqual(len(calls),2)
                self.assertEqual(client.metrics['calls'][0]['failure_code'],'API_ERROR')
                self.assertIsNone(client.metrics['total_tokens']);self.assertFalse(client.metrics['usage_available'])
            finally:budget.close()

        for status in [400,401,403,404]:
            with self.subTest(non_retryable_http=status),tempfile.TemporaryDirectory() as d:
                calls=[]
                def permanent(model,evidence,context):
                    calls.append(evidence)
                    raise urllib.error.HTTPError('https://fake',status,'permanent',{},None)
                budget=BudgetManager(dict(ai_requests=2))
                try:
                    client=JudgeClient(budget,d,transport=permanent,config=config)
                    result=client.classify('image_action_decision',item,{})
                    self.assertEqual(result['status'],'NEEDS_REVIEW')
                    self.assertEqual(len(calls),1)
                    self.assertEqual(result['failure_code'],'API_ERROR')
                finally:budget.close()

    def test_normal_v2_observation_and_record_only_score_pass(self):
        api=self.api();item=self.item();row=observation(item,confidence=0.0)
        api.validate_v2_schema(row);self.assertEqual(api.validate_v2_business(row,item)['confidence'],0.0)

    def test_missing_required_invalid_enum_undefined_fields_and_out_of_range_fail_schema(self):
        api=self.api();item=self.item();base=observation(item);cases=[]
        row=copy.deepcopy(base);row.pop('evidence_ids');cases.append(row)
        row=copy.deepcopy(base);row['decision']='ERASE_ANYTHING';cases.append(row)
        row=copy.deepcopy(base);row['do_shell']='not executable';cases.append(row)
        row=copy.deepcopy(base);row['watermarks']=[dict(kind='STORE_WATERMARK',bbox=[-.1,0,.2,.2],confidence=.9,preserve_overlap_risk='LOW')];cases.append(row)
        row=copy.deepcopy(base);row['watermarks']=[dict(kind='USER_ANNOTATION_RED_YELLOW_FRAME',bbox=[0,0,.2,.2],confidence=.9,preserve_overlap_risk='LOW')];cases.append(row)
        row=copy.deepcopy(base);row['product_identity']['unexpected']=True;cases.append(row)
        for row in cases:
            with self.subTest(row=row.get('decision')),self.assertRaisesRegex(ValueError,'SCHEMA_VALIDATION_FAILED'):api.validate_v2_schema(row)

    def test_sha_bbox_order_and_protected_print_are_business_failures(self):
        api=self.api();item=self.item()
        for kind in ['MANUFACTURER_LOGO','PRODUCT_PRINT','MODEL_TEXT','PACKAGING_PRINT','CREATOR_CREDIT']:
            row=observation(item,'REMOVE_TEXT',watermarks=[dict(kind=kind,action='REMOVE_TEXT',bbox=[.1,.1,.2,.2],confidence=.9,preserve_overlap_risk='LOW')])
            api.validate_v2_schema(row)
            with self.assertRaisesRegex(ValueError,'BUSINESS_VALIDATION_FAILED'):api.validate_v2_business(row,item)
        row=observation(item,image_sha256='b'*64);api.validate_v2_schema(row)
        with self.assertRaisesRegex(ValueError,'BUSINESS_VALIDATION_FAILED'):api.validate_v2_business(row,item)
        row=observation(item,'REMOVE_TEXT',watermarks=[dict(kind='STORE_WATERMARK',action='REMOVE_TEXT',bbox=[.3,.1,.2,.2],confidence=.9,preserve_overlap_risk='LOW')]);api.validate_v2_schema(row)
        with self.assertRaisesRegex(ValueError,'BUSINESS_VALIDATION_FAILED'):api.validate_v2_business(row,item)

    def test_business_conflicts_never_qualify_for_structural_retry(self):
        api=self.api();item=self.item()
        for changes in [dict(kind='PRODUCT_PRINT',preserve_overlap_risk='LOW'),dict(kind='STORE_WATERMARK',preserve_overlap_risk='HIGH')]:
            row=observation(item,'REMOVE_TEXT',watermarks=[dict(changes,action='REMOVE_TEXT',repair_mode='REGION',bbox=[.1,.1,.2,.2],confidence=.9)])
            self.assertFalse(api.retry_allowed('SCHEMA_VALIDATION_FAILED',row))
        self.assertTrue(api.retry_allowed('SCHEMA_VALIDATION_FAILED',observation(item)))
        self.assertFalse(api.retry_allowed('BUSINESS_VALIDATION_FAILED',observation(item)))

    def test_existing_validator_must_execute_full_schema_for_fresh_observations(self):
        from mye_c_automation.ai_judge.schemas import validate_result
        item=self.item();row=observation(item);row['watermarks']=[dict(kind='STORE_WATERMARK',bbox=[0,0,.2,.2],confidence=.9,preserve_overlap_risk='LOW',undefined_field=True)]
        with self.assertRaisesRegex(ValueError,'SCHEMA_VALIDATION_FAILED'):validate_result(row,'image_action_decision',item['id'],item)

    def test_client_records_schema_error_without_generating_mask(self):
        from mye_c_automation.ai_judge.client import JudgeClient
        from mye_c_automation.budget_manager import BudgetManager
        item=self.item()
        def response(model,evidence,context):
            row=observation(evidence);row['undefined_field']=True
            return dict(choices=[dict(message=dict(content=json.dumps(row)))],usage=dict(prompt_tokens=1,completion_tokens=1,total_tokens=2))
        with tempfile.TemporaryDirectory() as d:
            budget=BudgetManager(dict(ai_requests=1))
            try:
                client=JudgeClient(budget,d,transport=response,retries=0)
                result=client.classify('image_action_decision',item,{})
                self.assertEqual(result.get('failure_code'),'SCHEMA_VALIDATION_FAILED')
                self.assertEqual(client.metrics['calls'][-1]['failure_code'],'SCHEMA_VALIDATION_FAILED')
            finally:budget.close()

    def test_retries_are_bounded_and_business_failures_never_retry(self):
        from mye_c_automation.ai_judge.client import JudgeClient
        from mye_c_automation.budget_manager import BudgetManager
        item=self.item();config=dict(schema='model-gateway/v1',base_url='http://127.0.0.1:8788/v1',models=['deepseek-v4.1-flash'],max_output_tokens=4096,retries=0,timeout=150,vision_retry_limit=1)
        for mode,expected in [('schema-then-valid',2),('always-schema',2),('business',1)]:
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as d:
                calls=[]
                def response(model,evidence,context):
                    calls.append(evidence);row=observation(evidence)
                    if mode=='business':row=observation(evidence,'REMOVE_TEXT',watermarks=[dict(kind='PRODUCT_PRINT',action='REMOVE_TEXT',bbox=[.1,.1,.2,.2],confidence=.9,preserve_overlap_risk='LOW')])
                    elif mode=='always-schema' or len(calls)==1:row['extra']=True
                    return dict(choices=[dict(message=dict(content=json.dumps(row)))],usage=dict(prompt_tokens=1,completion_tokens=1,total_tokens=2))
                budget=BudgetManager(dict(ai_requests=3))
                try:
                    client=JudgeClient(budget,d,transport=response,config=config);result=client.classify('image_action_decision',item,{})
                    self.assertEqual(len(calls),expected)
                    self.assertEqual(result['status'],'VALIDATED' if mode=='schema-then-valid' else 'NEEDS_REVIEW')
                finally:budget.close()
