import tempfile
from pathlib import Path
import unittest
from mye_c_automation.executor.deployment_preflight import preflight

class PreflightTests(unittest.TestCase):
    def test_missing_identity_and_files_fail_closed(self):
        report=preflight({},inspector=lambda path: (_ for _ in ()).throw(OSError('unavailable')))
        self.assertFalse(report['ok'])
        self.assertTrue(report['blockers'])

    def test_untrusted_write_acl_and_same_account_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            config={'server_sid':'S-1-5-21-1','client_sid':'S-1-5-21-1'}
            for field in ['secret_file','credentials_file','nonce_database','evidence_root']:config[field]=tmp
            def inspect(path):
                return {'sid':'S-1-5-21-1','owner':'S-1-5-21-1','rules':[{'sid':'S-1-1-0','allow':True,'rights':2}]}
            report=preflight(config,tmp,inspect)
            self.assertFalse(report['ok'])
            self.assertTrue(any('write-capable' in x for x in report['blockers']))
            self.assertTrue(any('distinct' in x for x in report['blockers']))

    def test_process_identity_mismatch_rejected(self):
        def inspect(path):return {'sid':'S-1-5-21-99','owner':'S-1-5-18','rules':[{'sid':'S-1-5-18','allow':True,'rights':2}]}
        report=preflight({'server_sid':'S-1-5-21-1','client_sid':'S-1-5-21-2'},inspector=inspect)
        self.assertFalse(report['ok'])
        self.assertTrue(any('current process SID' in x for x in report['blockers']))
