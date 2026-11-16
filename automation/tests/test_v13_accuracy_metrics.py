import unittest
from mye_c_automation import shadow_evaluate


class AccuracyMetricsTests(unittest.TestCase):
    def row(self, identity, truth, prediction, usage_status='UNKNOWN', tokens=None):
        return dict(sample_id=identity,image_type='main',category='third_party_watermark',
                    detector='glm',ground_truth=truth,label_source='historical-human-record' if truth is not None else None,
                    prediction=prediction,usage_status=usage_status,tokens=tokens)

    def test_unlabeled_predictions_never_create_accuracy_or_zero_usage(self):
        result=shadow_evaluate.quality_metrics([self.row('unlabeled',None,True)])
        group=result['groups'][0]
        self.assertEqual(group['labeled'],0)
        self.assertIsNone(group['precision'])
        self.assertIsNone(group['recall_lower_bound'])
        self.assertIsNone(group['actual_tokens'])
        self.assertEqual(group['usage_status_counts'],{'UNKNOWN':1})

    def test_confusion_matrix_distinguishes_false_clean_from_abstention(self):
        rows=[self.row('tp',True,True),self.row('fp',False,True),self.row('fn',True,False),
              self.row('tn',False,False),self.row('defer',True,None)]
        group=shadow_evaluate.quality_metrics(rows)['groups'][0]
        self.assertEqual(group['confusion'],dict(tp=1,fp=1,fn=1,tn=1,undecided_positive=1,undecided_negative=0))
        self.assertEqual(group['precision'],.5)
        self.assertEqual(group['recall_decided'],.5)
        self.assertAlmostEqual(group['recall_lower_bound'],1/3)
        self.assertEqual(group['false_clean_rate'],.5)
        self.assertEqual(group['deferred_rate'],.2)

    def test_types_categories_and_detectors_are_separate_and_invalid_truth_rejected(self):
        a=self.row('a',True,True,'ACTUAL_REPORTED',123)
        b=dict(self.row('a',False,False,'ACTUAL_ZERO',0),image_type='sku',detector='kimi')
        result=shadow_evaluate.quality_metrics([a,b])
        self.assertEqual(len(result['groups']),2)
        self.assertEqual(result['groups'][0]['actual_tokens'],123)
        for bad in [dict(a,image_type='description'),dict(a,label_source=None),dict(a,tokens=None),dict(a,ground_truth='true')]:
            with self.assertRaises(ValueError):shadow_evaluate.quality_metrics([bad])
        with self.assertRaises(ValueError):shadow_evaluate.quality_metrics([a,a])
