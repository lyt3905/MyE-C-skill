import io,json,os,re,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from ai_judge import JudgeClient
from ai_judge.schemas import validate_result
from budget_manager import BudgetManager
from test_model_gateway_cli import PROFILE
from ai_judge.cache import cache_key

class SkuOutputContractTests(unittest.TestCase):
    def test_wire_has_one_complete_task_output_contract_and_exact_input_refs(self):
        item={'id':'SKU_ROW_001','task_type':'sku_match','sku_id':'SKU_ROW_001','image_id':'SKU_ROW_001',
              'sku_name':'with retail box','evidence_ids':['SKU_ROW_001']}
        result=dict(task_type='sku_match',item_id=item['id'],sku_id=item['sku_id'],image_id=item['image_id'],
                    decision='MATCH',confidence=.95,abstain=False,evidence_ids=item['evidence_ids'],
                    image_type='box',sku_packaging='with_box',shared_across_skus=False,missing_image=False)
        raw={'choices':[{'message':{'content':json.dumps(result)}}],
             'usage':{'prompt_tokens':90,'completion_tokens':10,'total_tokens':100}}
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'VLM_API_KEY':'fake'}):
            budget=BudgetManager({'ai_requests':2});sent=[]
            try:
                client=JudgeClient(budget,tmp,config=PROFILE,continue_model_errors=True)
                def send(req,timeout):sent.append(json.loads(req.data));return io.BytesIO(json.dumps(raw).encode())
                with patch('urllib.request.urlopen',side_effect=send):reply=client.classify('sku_match',item,{})
                self.assertEqual(reply['status'],'CLEAN')
                self.assertEqual(len(sent),2)
                for body in sent:
                    text=body['messages'][0]['content'][0]['text']
                    self.assertNotIn('Return JSON task_type,item_id,decision',text)
                    complete=re.search(r'Required root keys for sku_match: ([^.]+)',text)
                    self.assertIsNotNone(complete)
                    self.assertEqual(set(re.findall(r'[a-z_]+',complete.group(1))),set(result))
                    self.assertIn('mandatory even when abstain=true',text)
                    payload=json.JSONDecoder().raw_decode(text[text.index('{"item"'):])[0]
                    self.assertEqual(payload['item']['sku_id'],item['sku_id'])
                    self.assertEqual(payload['item']['image_id'],item['image_id'])
            finally:budget.close()

    def test_missing_or_wrong_sku_refs_remain_rejected(self):
        item={'id':'SKU_ROW_001','sku_id':'SKU_ROW_001','image_id':'SKU_ROW_001','evidence_ids':['SKU_ROW_001']}
        base=dict(task_type='sku_match',item_id=item['id'],decision='MATCH',confidence=.99,abstain=False,evidence_ids=item['evidence_ids'])
        for values in ({},{'sku_id':'wrong','image_id':'SKU_ROW_001'}):
            with self.subTest(values=values),self.assertRaises(ValueError):validate_result(dict(base,**values),'sku_match',item['id'],item)

    def test_prompt_changes_invalidate_sku_cache(self):
        import ai_judge.sku_match as module
        from unittest.mock import patch
        key=cache_key('sku_match',{'sha256':'A'},{},'model')
        with patch.object(module,'PROMPT',module.PROMPT+' changed'):
            self.assertNotEqual(key,cache_key('sku_match',{'sha256':'A'},{},'model'))

if __name__=='__main__':unittest.main()
