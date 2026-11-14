import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from account_coordination import account_lock

class AccountLockTests(unittest.TestCase):
    def test_account_lock_serializes_independent_roots(self):
        import threading,time
        with tempfile.TemporaryDirectory() as root:
            active=0;peak=0;counter=threading.Lock()
            def worker(index):
                nonlocal active,peak
                with account_lock('shared-account',directory=Path(root)):
                    with counter:active+=1;peak=max(peak,active)
                    time.sleep(.03)
                    with counter:active-=1
            with ThreadPoolExecutor(max_workers=3) as pool:list(pool.map(worker,range(3)))
            self.assertEqual(peak,1)
    def test_persistent_lock_file_does_not_require_manual_stale_cleanup(self):
        with tempfile.TemporaryDirectory() as root:
            for _ in range(2):
                with account_lock('shared-account',directory=Path(root)):pass
            self.assertEqual(len(list(Path(root).glob('*.lock'))),1)
