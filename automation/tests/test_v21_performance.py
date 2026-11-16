import unittest,tempfile,time
from pathlib import Path
from mye_c_automation.download_manager import download_unique
from mye_c_automation.ai_judge.cache import cache_key
class PerformanceTests(unittest.TestCase):
 def test_cache_ignores_job_paths(self):
  a=cache_key('watermark',{'id':'a','local':'C:/x','sha256':'abc'},{'pid':1,'title':'x'},'m')
  b=cache_key('watermark',{'id':'b','local':'D:/y','sha256':'abc'},{'pid':2,'title':'x'},'m')
  self.assertEqual(a,b)
  self.assertNotEqual(a,cache_key('watermark',{'sha256':'abc'},{'title':'y'},'m'))
 def test_download_ttl_and_limit(self):
  with tempfile.TemporaryDirectory() as root:
   calls=[]
   def download(url,path):
    calls.append(url);Path(path).write_bytes(b'1234')
   self.assertFalse(download_unique(['x'],root,download)['x']['cached'])
   self.assertTrue(download_unique(['x'],root,download)['x']['cached'])
   self.assertFalse(download_unique(['x'],root,download,ttl_seconds=0)['x']['cached'])
   self.assertIn('error',download_unique(['y'],root,download,max_bytes=2)['y'])
   self.assertEqual(len(calls),3)
class ConcurrencyTests(unittest.TestCase):
 def test_four_concurrent_and_cache_across_jobs(self):
  import threading,json
  from mye_c_automation.ai_judge import JudgeClient
  from mye_c_automation.budget_manager import BudgetManager
  active=0; peak=0; lock=threading.Lock(); barrier=threading.Barrier(4)
  def transport(model,item,context):
   nonlocal active,peak
   with lock: active+=1;peak=max(peak,active)
   barrier.wait(timeout=5)
   with lock: active-=1
   result={'task_type':'title_semantics','item_id':item['id'],'decision':'MATCH','confidence':1,'abstain':False,'evidence_ids':[item['id']]}
   return {'choices':[{'message':{'content':json.dumps(result)}}],'usage':{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2}}
  with tempfile.TemporaryDirectory() as root:
   b=BudgetManager({'ai_requests':4})
   c=JudgeClient(b,root,transport=transport,models=('m',),retries=0)
   items=[{'id':str(i),'task_type':'title_semantics','title':str(i),'evidence_ids':[str(i)]} for i in range(4)]
   results=c.process_queue({'schema':'ai-queue/v2','pid':1,'items':items},{'pid':1})
   self.assertEqual(peak,4);self.assertEqual(len(results),4)
   for item in items: item['id']='new'+item['id'];item['evidence_ids']=[item['id']]
   results=c.process_queue({'schema':'ai-queue/v2','pid':2,'items':items},{'pid':2})
   self.assertEqual(c.metrics['cache_hits'],4)
   self.assertEqual(b.snapshot()['used']['ai_requests'],4)
if __name__=='__main__': unittest.main()
