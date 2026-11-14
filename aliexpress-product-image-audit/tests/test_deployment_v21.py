import tempfile
import unittest
from pathlib import Path
from executor.deployment_preflight import preflight
class DeploymentV21(unittest.TestCase):
 def test_unproven_account_isolation_blocks_activation(self):
  result=preflight({'server_sid':'server','client_sid':'agent'},inspector=lambda p:{'sid':'server','owner':'server','protected':True,'rules':[{'sid':'server','allow':True,'rights':0x10000000}]})
  self.assertFalse(result['ok'])
  self.assertTrue(any('cross-account' in b for b in result['blockers']))
 def test_secret_read_ace_rejected(self):
  with tempfile.TemporaryDirectory() as tmp:
   secret=Path(tmp)/'secret';secret.touch()
   result=preflight({'server_sid':'server','client_sid':'agent','secret_file':str(secret)},inspector=lambda p:{'sid':'server','owner':'server','protected':True,'rules':[{'sid':'agent','allow':True,'rights':0x80000000}]})
   self.assertTrue(any('secret-readable' in b for b in result['blockers']))
