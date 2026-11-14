import tempfile,unittest
from unittest.mock import Mock
from executor.service import ExecutorService
from budget_manager import BudgetManager,BudgetExceeded
from product_state import canonical_state_hash
class ExecutorBudgetTests(unittest.TestCase):
 def test_zero_save_budget_blocks_writer(self):
  with tempfile.TemporaryDirectory() as folder:
   b=BudgetManager({'site_save':0,'translate_title':0}); writer=Mock();writer.product.return_value={'id':1,'shopId':7,'images':{'main':['https://x/a'],'detail':['https://x/b']}}
   plan=dict(schema='token-opt-plan/v2',job_id='JOB_a',pid=1,shop=7,workflow_version='token-opt-v2',policy_version='v2',precondition={'state_sha256':canonical_state_hash(writer.product.return_value)},evidence_refs=[],ai_judgement_refs=[],desired={'titleEn':'Changed'},post_actions={},review={'status':'RESOLVED'})
   from pathlib import Path
   import hashlib
   source=Path(folder)/'evidence.json';source.write_bytes(b'{}')
   plan['evidence_refs']=[{'path':source.name,'sha256':hashlib.sha256(source.read_bytes()).hexdigest()}]
   with self.assertRaises(BudgetExceeded):ExecutorService(Mock(),writer,folder,budget=b).execute(plan,ticket={},dry_run=False)
   writer.save.assert_not_called();b.close()
