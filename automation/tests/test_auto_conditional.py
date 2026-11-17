import unittest,tempfile,json
from pathlib import Path
from mye_c_automation.candidate_quality import CandidateQualityGate
from mye_c_automation.remedy_planner import RemedyPlanner
from test_auto_remedy import RemedyTests,Inspector
class ConditionalDecisionTests(unittest.TestCase):
 def test_machine_validation_resolves_conditional_before_compilation(self):
  for passed in (True,False):
   with self.subTest(passed=passed),tempfile.TemporaryDirectory() as root:
    item,twin=RemedyTests().fixture(root)
    class Observing(Inspector):
     def inspect(self,*args):
      state=json.loads((Path(root)/'conditional_decisions.json').read_text())['items'][-1]
      self_test.assertEqual(state['decision'],'AUTO_CONDITIONAL')
      return dict(super().inspect(*args),source_clean=passed)
    self_test=self
    result=RemedyPlanner(root,CandidateQualityGate(Observing())).plan(item,[twin],{})
    states=json.loads((Path(root)/'conditional_decisions.json').read_text())['items']
    self.assertEqual(states[-1]['decision'],'AUTO_CONDITIONAL' if passed else 'DEFERRED')
    self.assertEqual(bool(result),passed)
