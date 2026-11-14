import tempfile,unittest,uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import test_auto_real_auditor_workflow as helpers

class CrossShopWorkflowTests(unittest.TestCase):
    def test_E29_two_real_auditor_jobs_do_not_mix_shared_current_shop(self):
        with tempfile.TemporaryDirectory() as root:
            context={'shop':None,'saves':[]};account='fake-'+uuid.uuid4().hex
            def worker(identity):
                pid,shop=identity
                return helpers.RealAuditorWorkflowTests().execute(Path(root)/str(pid),'erase',shop=shop,pid=pid,coordination_key=account,shop_context=context)[0]
            with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(worker,[(1,7),(2,4)]))
            self.assertTrue(all(r['status'] in {'AUTO_VERIFIED','PARTIALLY_AUTO_FIXED'} for r in results),results)
            self.assertEqual(set(context['saves']),{(1,7),(2,4)})
