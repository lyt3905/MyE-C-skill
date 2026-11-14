from watermark_fixtures import exhaustive
from PIL import Image
import tempfile, unittest
from ai_judge import JudgeClient
from budget_manager import BudgetManager
class JudgeTests(unittest.TestCase):
    def test_invalid_response_never_clean(self):
        with tempfile.TemporaryDirectory() as root:
            b=BudgetManager({'ai_requests':45})
            c=JudgeClient(b,root,transport=lambda *a:{'choices':[{'message':{'content':'{}'}}]})
            self.assertEqual(c.classify('watermark',{'id':'A','dimensions':[800,800]},{} )['status'],'NEEDS_REVIEW')
            self.assertEqual(c.metrics['requests'],1)  # Schema refusal is not a recoverable network failure.
    def test_empty_queue_no_calls(self):
        with tempfile.TemporaryDirectory() as root:
            c=JudgeClient(BudgetManager({'ai_requests':45}),root,transport=lambda *a:self.fail())
            self.assertEqual(c.process_queue({'schema':'ai-queue/v2','pid':1,'items':[]},{'pid':1}),{})
    def test_timeout_counted(self):
        def timeout(*args): raise TimeoutError()
        with tempfile.TemporaryDirectory() as root:
            c=JudgeClient(BudgetManager({'ai_requests':45}),root,transport=timeout)
            self.assertEqual(c.classify('watermark',{'id':'A','dimensions':[800,800]}, {})['status'],'NEEDS_REVIEW')
            self.assertEqual(c.metrics['requests'],3)
    def test_cache_context_isolated(self):
        from ai_judge.cache import cache_key
        self.assertNotEqual(cache_key('sku_match',{'sha256':'a'},{'sku':'red'},'m'),cache_key('sku_match',{'sha256':'a'},{'sku':'blue'},'m'))
    def test_boolean_confidence_rejected(self):
        from ai_judge.schemas import validate_result
        with self.assertRaises(ValueError):
            validate_result({'task_type':'title_semantics','item_id':'A','decision':'MATCH','confidence':True,'abstain':False,'evidence_ids':['A']},'title_semantics','A')
    def test_unique_image_budget_and_missing_usage(self):
        import json
        from pathlib import Path
        with tempfile.TemporaryDirectory() as root:
            image=Path(root)/'a.jpg'; Image.new('RGB',(800,800),'white').save(image)
            result={'task_type':'watermark','item_id':'A','classification':'product_print','owner':'manufacturer','location':'center','confidence':.95,'abstain':False,'evidence_ids':['A']}
            c=JudgeClient(BudgetManager({'ai_requests':45,'full_resolution_images':1}),Path(root)/'cache',transport=lambda *a:{'choices':[{'message':{'content':json.dumps(exhaustive(result))}}]})
            self.assertEqual(c.classify('watermark',{'task_type':'watermark','id':'A','local':str(image),'evidence_ids':['A']},{})['status'],'CLEAN')
            self.assertEqual(c.metrics['requests'],2)
            self.assertFalse(c.metrics['usage_available'])
            self.assertIsNone(c.metrics['total_tokens'])
    def test_pipeline_context_changes_with_sku_and_title(self):
        from workflow_v2_pipeline import product_context
        from ai_judge.cache import cache_key
        job={'pid':1,'shop_id':7}
        a=product_context({'title':'A','skus':[{'name':'red'}]},job,{})
        b=product_context({'title':'A','skus':[{'name':'blue'}]},job,{})
        c=product_context({'title':'B','skus':[{'name':'red'}]},job,{})
        self.assertNotEqual(cache_key('sku_match',{},a,'m'),cache_key('sku_match',{},b,'m'))
        self.assertNotEqual(cache_key('sku_match',{},a,'m'),cache_key('sku_match',{},c,'m'))
