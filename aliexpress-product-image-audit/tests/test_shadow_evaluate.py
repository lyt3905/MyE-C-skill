import unittest
from shadow_evaluate import evaluate

class ShadowTests(unittest.TestCase):
    def test_counts_and_no_automatic_acceptance(self):
        row = dict(sample_id='x', human_issue=True, baseline=dict(issue=True,tokens=10,latency_ms=20), candidate=dict(issue=False,tokens=5,latency_ms=10))
        report = evaluate([row])
        self.assertEqual(report['results']['candidate']['false_negative'], 1)
        self.assertFalse(report['accepted'])
        with self.assertRaises(ValueError): evaluate([row,row])
    def test_invalid_measurements(self):
        with self.assertRaises(ValueError): evaluate([])
        with self.assertRaises(ValueError): evaluate([dict(sample_id='x',human_issue='yes',baseline={},candidate={})])
