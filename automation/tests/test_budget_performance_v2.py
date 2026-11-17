import tempfile
import unittest
from pathlib import Path
from mye_c_automation.budget_manager import BudgetManager, BudgetExceeded
from mye_c_automation.download_manager import download_unique

class PersistencePerformanceTests(unittest.TestCase):
    def test_budget_survives_restart(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'budget.db'
            a=BudgetManager({'ai':1}, path); a.reserve('ai'); a.close()
            b=BudgetManager({'ai':1}, path)
            with self.assertRaises(BudgetExceeded): b.reserve('ai')
            b.close()
    def test_download_dedup_failure_and_cache(self):
        with tempfile.TemporaryDirectory() as root:
            calls=[]
            def download(url,path):
                calls.append(url)
                if url=='bad': raise IOError('offline')
                Path(path).write_bytes(b'image')
            result=download_unique(['ok','ok','bad'],root,download)
            self.assertEqual(sorted(calls),['bad','ok'])
            self.assertIn('error',result['bad'])
            self.assertTrue(download_unique(['ok'],root,download)['ok']['cached'])
            self.assertFalse(list(Path(root).glob('*.tmp')))
