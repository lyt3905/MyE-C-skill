import copy,json,tempfile,unittest,urllib.error
from pathlib import Path
from unittest.mock import Mock,patch
from mye_c_automation.job_manager import JobManager
from mye_c_automation.budget_manager import BudgetManager
from mye_c_automation.ai_judge import JudgeClient
from mye_c_automation.automation_policy import AutomationPolicy
from test_auto_decision import CONFIG
from mye_c_automation import title_generation as titles

TITLE='Hot Sale Transformation NewAge NA-H74 NAH74 Megatank Action Figures Collection Gifts'
def reply(title=TITLE,warnings=None,finish='stop'):
    return dict(choices=[dict(finish_reason=finish,message=dict(content=json.dumps(dict(titleEn=title,modelCode='NA-H74',warnings=warnings or [])),reasoning_content='raw thinking retained'))])

class TitleGenerationTests(unittest.TestCase):
    def product(self):return dict(id=1,title='NewAge NA-H74 威震天 变形玩具',titleEn='old',identityJson={'modelCode':'NA-H74'},descriptionJson='PRIVATE BODY',price=123,skus=[dict(skuName='NA-H74 no retail box',price=456,skuImageUrl='PRIVATE URL')])
    def setup_job(self,root,transport,enabled=True,retries=2):
        manager=JobManager(Path(root)/'jobs');job=manager.create(1,7,{'ai_requests':20},mode='auto_apply',image_workflow='v2',model_budget={'mode':'RECORD_ONLY','usage_source':'FAKE_TRANSPORT'})
        job=manager.bind_input(job['job_id'],self.product());directory=manager.directory(job['job_id'])
        (directory/'audit_product.json').write_text(json.dumps(self.product()),encoding='utf-8')
        policy=AutomationPolicy(dict(CONFIG,allow_actions={**CONFIG['allow_actions'],'TITLE_REWRITE':enabled},title_rewrite={'retries':retries,'retry_delay':0}))
        budget=BudgetManager(job['budget'],directory/'budget.sqlite');budget.configure_model_budget(job['model_budget'],job['job_id'])
        judge=JudgeClient(budget,directory/'judge_cache',transport=transport,retries=0)
        return directory,job,policy,budget,judge
    def test_reference_payload_is_text_only_and_excludes_body_prices_images(self):
        p=self.product();before=copy.deepcopy(p);messages=titles.make_messages(p,7)
        data=json.loads(messages[1]['content']);self.assertEqual(data['shop_prefix'],'Hot Sale')
        self.assertEqual(set(data),{'title','titleEn','identityJson','skus','shop','shop_prefix'})
        self.assertEqual(data['skus'],[{'skuName':'NA-H74 no retail box'}]);self.assertEqual(p,before)
        self.assertNotIn('PRIVATE',json.dumps(messages));self.assertIn('Megatank',messages[0]['content']);self.assertIn('Upgrade Kit',messages[0]['content'])
    def test_reference_format_and_shop_contract(self):
        self.assertEqual(titles.parse_result(reply(),7)['titleEn'],TITLE)
        for raw,shop in [(reply(),4),(reply('Hot Sale Hasbro '+titles.SUFFIX),7),(reply('Hot Sale Megatron '+titles.SUFFIX),7),(reply(finish='length'),7),(reply('x'*121),7)]:
            with self.subTest(shop=shop),self.assertRaises((ValueError,KeyError,TypeError)):titles.parse_result(raw,shop)

    def test_confirmed_facts_are_separate_model_input_without_product_mutation(self):
        p=self.product();before=copy.deepcopy(p);facts=['H36 and H40 are sold together as a two-figure set.']
        data=json.loads(titles.make_messages(p,7,confirmed_facts=facts)[1]['content'])
        self.assertEqual(data['confirmed_facts'],facts);self.assertEqual(p,before)

    def test_confirmed_facts_are_frozen_and_verified_in_generation(self):
        with tempfile.TemporaryDirectory() as root:
            transport=Mock(return_value=reply());d,j,p,b,judge=self.setup_job(root,transport)
            p=AutomationPolicy(dict(p.config,title_rewrite={'retries':0,'retry_delay':0,'confirmed_facts':['Two figures together']}))
            try:
                row=titles.prepare_title(d,j,p,judge=judge)[0]
                self.assertEqual(json.loads(transport.call_args.args[1]['messages'][1]['content'])['confirmed_facts'],['Two figures together'])
                f=d/'title_generation.json';r=json.loads(f.read_text());r['confirmed_facts']=['Different product'];f.write_text(json.dumps(r))
                with self.assertRaisesRegex(ValueError,'TITLE_INPUT_BINDING'):titles.verify_title(d,row,self.product())
            finally:b.close()
    def test_first_success_is_cached_without_second_review_and_uses_same_ledger(self):
        with tempfile.TemporaryDirectory() as root:
            transport=Mock(return_value=reply());d,j,p,b,judge=self.setup_job(root,transport)
            try:
                rows=titles.prepare_title(d,j,p,judge=judge);again=titles.prepare_title(d,j,p,judge=judge)
                self.assertEqual(rows,again);self.assertEqual(rows[0]['action'],'TITLE_REWRITE');self.assertEqual(rows[0]['titleEn'],TITLE)
                transport.assert_called_once();self.assertEqual(transport.call_args.args[0],'deepseek-v4.1-flash')
                record=json.loads((d/'title_generation.json').read_text());self.assertIsNone(record['calls'][0]['usage']);self.assertEqual(record['calls'][0]['raw_response']['choices'][0]['message']['reasoning_content'],'raw thinking retained')
                self.assertEqual(b._db.execute('SELECT count(*) FROM model_calls').fetchone()[0],1)
                self.assertEqual(b.snapshot()['used'].get('full_resolution_images',0),0)
                titles.verify_title(d,rows[0],self.product())
            finally:b.close()
    def test_invalid_or_timeout_retries_until_first_success(self):
        with tempfile.TemporaryDirectory() as root:
            transport=Mock(side_effect=[TimeoutError(),reply(finish='length'),reply(),reply()]);d,j,p,b,judge=self.setup_job(root,transport)
            try:
                rows=titles.prepare_title(d,j,p,judge=judge);self.assertEqual(rows[0]['action'],'TITLE_REWRITE');self.assertEqual(transport.call_count,3)
                record=json.loads((d/'title_generation.json').read_text());self.assertEqual(len(record['calls']),3);self.assertEqual(record['calls'][1]['raw_response']['choices'][0]['finish_reason'],'length')
            finally:b.close()
    def test_valid_warnings_are_recorded_and_failures_defer_title(self):
        for response in [reply(warnings=['角色需确认']),TimeoutError(),urllib.error.HTTPError('https://fake',401,'no',{},None)]:
            with self.subTest(kind=type(response).__name__),tempfile.TemporaryDirectory() as root:
                transport=Mock(side_effect=response) if isinstance(response,Exception) else Mock(return_value=response)
                d,j,p,b,judge=self.setup_job(root,transport)
                try:
                    row=titles.prepare_title(d,j,p,judge=judge)[0];self.assertEqual(row['action'],'WEB_DEFER' if isinstance(response,Exception) else 'TITLE_REWRITE');self.assertEqual(row['target'],{'field':'titleEn'})
                    if not isinstance(response,Exception):self.assertEqual(titles.verify_title(d,row,self.product())['warnings'],['角色需确认'])
                    if not isinstance(response,TimeoutError):self.assertEqual(transport.call_count,1)
                finally:b.close()
    def test_permission_disabled_never_calls_model(self):
        with tempfile.TemporaryDirectory() as root:
            transport=Mock(side_effect=AssertionError('disabled'));d,j,p,b,judge=self.setup_job(root,transport,enabled=False)
            try:self.assertEqual(titles.prepare_title(d,j,p,judge=judge),[]);transport.assert_not_called()
            finally:b.close()
    def test_tampered_title_or_raw_response_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            d,j,p,b,judge=self.setup_job(root,Mock(return_value=reply()))
            try:
                row=titles.prepare_title(d,j,p,judge=judge)[0]
                with self.assertRaises(ValueError):titles.verify_title(d,dict(row,titleEn=TITLE.replace('NewAge','Other')),self.product())
                f=d/'title_generation.json';v=json.loads(f.read_text());v['calls'][0]['raw_response']=reply(TITLE.replace('NewAge','Other'));f.write_text(json.dumps(v))
                with self.assertRaises(ValueError):titles.verify_title(d,row,self.product())
            finally:b.close()

    def test_cache_hit_with_new_client_keeps_original_metrics_bytes(self):
        with tempfile.TemporaryDirectory() as root:
            d,j,p,b,judge=self.setup_job(root,Mock(return_value=reply()))
            try:
                first=titles.prepare_title(d,j,p,judge=judge);before=(d/'title_ai_metrics.json').read_bytes()
                never=Mock(side_effect=AssertionError('cached result requested again'));other=JudgeClient(b,d/'judge_cache',transport=never,retries=0)
                self.assertEqual(titles.prepare_title(d,j,p,judge=other),first);never.assert_not_called()
                self.assertEqual((d/'title_ai_metrics.json').read_bytes(),before)
            finally:b.close()
    def test_real_request_shape_uses_text_messages_and_project_model_settings(self):
        with tempfile.TemporaryDirectory() as root:
            d,j,p,b,judge=self.setup_job(root,None)
            try:
                response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock();response.read=Mock(return_value=json.dumps(reply()).encode())
                with patch.dict('os.environ',{'VLM_API_KEY':'FAKE_KEY'}),patch('mye_c_automation.ai_judge.client._open_model_request',return_value=response) as opened:
                    titles.prepare_title(d,j,p,judge=judge)
                request=opened.call_args.args[0];body=json.loads(request.data)
                self.assertEqual(body['messages'],titles.make_messages(self.product(),7));self.assertEqual(body['response_format'],{'type':'json_object'});self.assertEqual(body['max_tokens'],judge.max_output_tokens)
                self.assertEqual(request.get_header('Authorization'),'Bearer FAKE_KEY')
            finally:b.close()
