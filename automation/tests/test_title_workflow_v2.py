import copy,io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import test_process_workflow as helpers
from test_title_generation_v2 import TITLE,reply

class TitleWorkflowTests(unittest.TestCase):
    def fixture(self,root,warnings=None):
        h=helpers.ProcessWorkflowTests();f=h.fixture(root)
        path=f['cfg']/'automation.local.json';policy=json.loads(path.read_text());policy['allow_actions']['TITLE_REWRITE']=True;policy['title_rewrite']={'retries':0,'retry_delay':0};path.write_text(json.dumps(policy))
        f['writer'].state.update(title='NewAge NA-H74 威震天 变形玩具',titleEn='old title',titleTranslationZh='原中文',identityJson=json.dumps({'modelCode':'OLD','other':'protected'}))
        f['original']=copy.deepcopy(f['writer'].state);old=f['model'];f['title_calls']=0
        def model(request,timeout):
            body=json.loads(request.data)
            if body['messages'][0]['role']=='system':
                f['title_calls']+=1;f['counters']['model_calls']+=1
                self.assertNotIn('descriptionJson',body['messages'][1]['content'])
                return io.BytesIO(json.dumps(reply(warnings=warnings)).encode())
            return old(request,timeout)
        f['model']=model;return h,f
    def test_public_process_combines_title_and_images_in_one_verified_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);h,f=self.fixture(root)
            with patch('mye_c_automation.title_rewrite.rewrite_title',side_effect=AssertionError('legacy title generator must not run')):
                code,result,text=h.invoke(root,f)
            self.assertEqual(code,0,text);self.assertEqual(result['status'],'AUTO_VERIFIED',text);self.assertTrue(result['independent_verification']['title_exact'])
            after=f['writer'].state;self.assertEqual(after['titleEn'],TITLE);self.assertEqual(f['counters']['saves'],1);self.assertEqual(f['title_calls'],1)
            for key in ('title','titleTranslationZh','identityJson','price','weight','presale','status'):self.assertEqual(after[key],f['original'][key])
            self.assertNotIn('raw thinking',text);self.assertEqual(result['title']['titleEn'],TITLE)
            self.assertTrue(result['title']['applied'])
            plan=json.loads((Path(result['evidence_directory'])/'plan.v2.json').read_text());self.assertNotIn('translate_title',plan['post_actions']);self.assertNotIn('identityJson',plan['desired'])
            report=json.loads((Path(result['evidence_directory'])/'report_data.json').read_text());self.assertEqual(report['title']['titleEn'],TITLE)
            self.assertEqual(report['ai']['metrics_completeness'],'VERIFIED')
    def test_warning_is_retained_without_overriding_first_valid_title(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);h,f=self.fixture(root,warnings=['角色不确定']);code,result,text=h.invoke(root,f)
            self.assertEqual(result['status'],'AUTO_VERIFIED',text);self.assertEqual(f['writer'].state['titleEn'],TITLE);self.assertEqual(f['counters']['saves'],1)
            self.assertEqual(result['title']['warnings'],['角色不确定']);self.assertEqual(f['title_calls'],1)
    def test_audit_only_generates_title_without_any_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);h,f=self.fixture(root);code,result,text=h.invoke(root,f,'--audit-only')
            self.assertEqual(result['status'],'AUDITED',text);self.assertEqual(result['title']['titleEn'],TITLE);self.assertEqual(f['counters']['saves'],0);self.assertEqual(f['writer'].state,f['original'])
    def test_lost_save_response_resume_does_not_repeat_title_or_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);h,f=self.fixture(root);save=f['writer'].save
            def lost(*args,**kwargs):save(*args,**kwargs);raise TimeoutError('response lost')
            with patch.object(f['writer'],'save',side_effect=lost):_,first,_=h.invoke(root,f)
            before=dict(f['counters']);code,result,text=h.invoke(root,f,'--resume',first['job_id'])
            self.assertEqual(result['status'],'AUTO_VERIFIED',text);self.assertEqual(f['counters']['saves'],before['saves']);self.assertEqual(f['counters']['model_calls'],before['model_calls']);self.assertEqual(f['title_calls'],1)
    def test_fake_cli_includes_title_and_uses_independent_package_prompt(self):
        from mye_c_automation.cli import main
        with tempfile.TemporaryDirectory() as tmp:
            output=io.StringIO()
            from contextlib import redirect_stdout
            with redirect_stdout(output):code=main(['fake','--scenario','twin','--with-title','--data-root',tmp])
            self.assertEqual(code,0,output.getvalue());result=json.loads(output.getvalue());self.assertEqual(result['status'],'AUTO_VERIFIED');self.assertTrue(result['title_enabled']);self.assertTrue(result['title']['applied'])

    def test_title_failure_does_not_block_independent_image_repairs(self):
        import urllib.error
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);h,f=self.fixture(root);old=f['model']
            def failed(request,timeout):
                if json.loads(request.data)['messages'][0]['role']=='system':raise urllib.error.HTTPError('https://fake',401,'failed',{},None)
                return old(request,timeout)
            f['model']=failed;code,result,text=h.invoke(root,f)
            self.assertEqual(result['status'],'PARTIALLY_AUTO_FIXED',text);self.assertEqual(f['writer'].state['titleEn'],'old title');self.assertEqual(f['counters']['saves'],1);self.assertEqual(result['title']['status'],'FAILED')

    def test_independent_title_mismatch_cannot_be_auto_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);h,f=self.fixture(root);reader=f['reader']
            def changed(config):
                r=reader(config);product=r.product
                def observed(pid):
                    value=product(pid)
                    if f['counters']['saves']:value['titleEn']='unexpected title'
                    return value
                r.product=observed;return r
            f['reader']=changed;code,result,text=h.invoke(root,f)
            self.assertNotEqual(result['status'],'AUTO_VERIFIED');self.assertFalse(result['independent_verification']['title_exact'])

    def test_title_alone_uses_same_executor_without_translation(self):
        from mye_c_automation.fake import run_fake
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'logs').mkdir()
            result=run_fake(root,'keep',with_title=True)
            self.assertEqual(result['status'],'AUTO_VERIFIED');self.assertEqual(result['saves'],1);self.assertEqual(result['uploads'],0)
