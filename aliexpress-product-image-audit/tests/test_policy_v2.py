import tempfile, unittest
from policy_engine import evaluate
class PolicyTests(unittest.TestCase):
    def test_preserve(self):
        self.assertEqual(evaluate({'status':'CLEAN','results':[{'task_type':'watermark','confidence':.99,'abstain':False,'classification':'social_account_signature'}]}),'KEEP')
    def test_unknown_reviews(self):
        self.assertEqual(evaluate({'status':'CLEAN','results':[{'task_type':'watermark','confidence':.99,'abstain':False,'classification':'unknown'}]}),'NEEDS_REVIEW')
