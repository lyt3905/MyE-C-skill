"""Real queue/client path with synthetic responses, no model or site calls."""
import json
from pathlib import Path
import tempfile
import unittest
from ai_judge import JudgeClient
from budget_manager import BudgetManager
from test_8788_real_validation import response

class FullAuditModelContinuationTests(unittest.TestCase):
    def exercise(self, broken_model, broken_choices=None):
        with tempfile.TemporaryDirectory() as tmp:
            calls=[]
            budget=BudgetManager({'ai_requests':8})
            def fake(model,item,context):
                calls.append((item['id'],model))
                raw=response(item,model)
                if item['id']=='A' and model==broken_model:
                    raw['choices']=broken_choices if broken_choices is not None else [{'message':{'content':'{}'}}]
                return raw
            try:
                client=JudgeClient(budget,Path(tmp)/'cache',transport=fake,models=('a','b'),retries=0,continue_model_errors=True)
                queue={'schema':'ai-queue/v2','pid':1,'items':[{'id':i,'task_type':'watermark','dimensions':[800,800],'sha256':i*64,'evidence_ids':[i]} for i in ('A','B')]}
                result=client.process_queue(queue,{'pid':1})
                self.assertEqual(set(calls),{(i,m) for i in ('A','B') for m in ('a','b')})
                self.assertEqual(len(calls),4)
                self.assertEqual(result['A']['status'],'NEEDS_REVIEW')
                self.assertEqual(result['A']['models'],['a','b'])
                index=0 if broken_model=='a' else 1
                self.assertEqual(result['A']['results'][index],{})
                self.assertEqual(result['A']['results'][1-index]['item_id'],'A')
                self.assertEqual(result['A']['model_errors'][0]['model'],broken_model)
                self.assertEqual(result['B']['status'],'CLEAN')
                self.assertEqual(client.metrics['requests'],4)
                self.assertEqual(sum('raw_response' in r for r in client.metrics['calls']),4)
            finally:budget.close()

    def test_first_model_schema_error_preserves_second_model_slot(self):self.exercise('a')
    def test_second_model_schema_error_keeps_first_result(self):self.exercise('b')
    def test_empty_choices_is_recorded_and_remaining_model_continues(self):self.exercise('a',[])

    def test_truncated_valid_json_stays_unknown_and_second_model_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            budget=BudgetManager({'ai_requests':2});calls=[]
            def transport(model,item,context):
                calls.append(model);raw=response(item,model)
                if model=='a':raw['choices'][0]['finish_reason']='length'
                return raw
            try:
                c=JudgeClient(budget,tmp,transport=transport,models=('a','b'),retries=0,continue_model_errors=True)
                result=c.classify('watermark',{'id':'A','task_type':'watermark','dimensions':[800,800],'evidence_ids':['A']},{})
                self.assertEqual(calls,['a','b'])
                self.assertEqual(result['status'],'NEEDS_REVIEW')
                self.assertEqual(result['results'][0],{})
            finally:budget.close()

    def test_budget_exhaustion_still_prevents_the_second_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            budget=BudgetManager({'ai_requests':1});calls=[]
            def transport(model,item,context):
                calls.append(model);return {'choices':[{'message':{'content':'{}'}}]}
            try:
                c=JudgeClient(budget,tmp,transport=transport,models=('a','b'),retries=0,continue_model_errors=True)
                result=c.classify('watermark',{'id':'A','task_type':'watermark','dimensions':[800,800],'evidence_ids':['A']},{})
                self.assertEqual(calls,['a'])
                self.assertEqual(result['error'],'BUDGET_EXCEEDED')
                self.assertEqual(budget.snapshot()['used']['ai_requests'],1)
            finally:budget.close()

    def test_standard_full_product_entry_reports_all_positions_after_first_schema_error(self):
        import test_full_product_audit as fixtures
        from copy import deepcopy
        from unittest.mock import patch
        from job_manager import atomic_json
        from full_product_audit import run_full_audit,build_inventory
        helper=fixtures.FullProductAuditTests()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);product,images=helper.fixture(root)
            expected=helper.decisions(build_inventory(product,images));calls=[]
            class Reader:
                def current_shop(self):return 7
                def account_fingerprint(self):return 'a'*64
                def product(self,pid):return deepcopy(product)
                def save(self,*args,**kwargs):raise AssertionError('No writes')
            def auditor(pid,shop,output_dir,site):
                atomic_json(output_dir/'audit_product.json',product)
                atomic_json(output_dir/'audit_raw.json',{'pid':pid,'images':images})
                atomic_json(output_dir/'audit_flags.json',{'pid':pid,'summary':{'ocr_enabled':True},'duplicates':[],'anomalies':[]})
            def transport(model,item,context):
                calls.append((item['id'],model))
                payload='{}' if item['id']==next(iter(expected)) and model=='glm-5v-turbo' else json.dumps(expected[item['id']]['results'][0])
                return dict(model=model,usage=dict(prompt_tokens=90,completion_tokens=10,total_tokens=100),
                            choices=[dict(message=dict(content=payload))])
            def factory(*args,**kwargs):
                self.assertTrue(kwargs['continue_model_errors'])
                return JudgeClient(*args,transport=transport,**kwargs)
            templates=root/'templates.json'
            atomic_json(templates,{'required_shop_ids':[],'no_applicable_shop_ids':[7],'templates':[]})
            with patch('ai_judge.JudgeClient',side_effect=factory):
                report=run_full_audit(root/'jobs',1,7,Reader(),auditor=auditor,template_config=templates)
            self.assertEqual(len(calls),12)
            self.assertEqual(report['image_and_reference_count'],7)
            self.assertFalse(report['audit_complete'])
            self.assertEqual(report['site_save_calls'],0)
            self.assertEqual(report['upload_calls'],0)
            directory=next((root/'jobs').glob('JOB_*'))
            results=json.loads((directory/'full_ai_judgements.json').read_text(encoding='utf-8'))
            self.assertEqual(len(results),6)
            self.assertTrue((directory/'full_audit_report.json').exists())
            self.assertEqual(len(json.loads((directory/'full_ai_metrics.json').read_text(encoding='utf-8'))['calls']),12)

    def test_transport_failure_does_not_enable_extra_model_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            budget=BudgetManager({'ai_requests':8});calls=[]
            def fake(*args):calls.append(1);raise TimeoutError()
            try:
                c=JudgeClient(budget,tmp,transport=fake,models=('a','b'),retries=0,continue_model_errors=True)
                result=c.classify('watermark',{'id':'A','task_type':'watermark','dimensions':[800,800],'evidence_ids':['A']},{})
                self.assertEqual(len(calls),1)
                self.assertEqual(result['error'],'TimeoutError')
            finally:budget.close()

if __name__=='__main__':unittest.main()
