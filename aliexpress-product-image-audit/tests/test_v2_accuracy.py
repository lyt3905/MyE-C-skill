import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from PIL import Image
import shadow_evaluate


def sample(digest='a'*64,**changes):
    row=dict(schema='v2-accuracy-sample/v1',image_sha256=digest,image_type='MAIN',
        evidence_kind='FAKE',human_confirmed=False,label_source='synthetic-test',
        ground_truth_action='DELETE',prediction_action='DELETE',confidence=.95,abstain=False,
        ground_truth_retail_box='ABSENT',prediction_retail_box='ABSENT',
        repair_pass=None,severe_error=False,sku_selection_correct=None)
    row.update(changes);return row


class V2AccuracyTests(unittest.TestCase):
    def test_empty_labels_do_not_invent_accuracy_or_release(self):
        report=shadow_evaluate.v2_quality_metrics([])
        self.assertEqual(report['status'],'NOT_EVALUATED')
        self.assertIsNone(report['real']['actions']['DELETE']['precision'])
        self.assertEqual(report['real']['unique_images'],0)
        self.assertFalse(report['statistical_gates_met']);self.assertFalse(report['release_authorized'])

    def test_same_sha_across_business_positions_counts_once(self):
        a=sample();b=dict(a,image_type='DETAIL')
        report=shadow_evaluate.v2_quality_metrics([a,b])
        self.assertEqual(report['synthetic']['unique_images'],1)
        self.assertEqual(report['duplicates_merged'],1)
        self.assertEqual(report['synthetic']['actions']['DELETE']['labeled'],1)
        self.assertEqual(report['real']['unique_images'],0)

    def test_conflicting_same_sha_is_rejected(self):
        a=sample()
        for b in (dict(a,ground_truth_action='KEEP'),dict(a,prediction_action='KEEP'),dict(a,evidence_kind='REAL_SHADOW')):
            with self.assertRaisesRegex(ValueError,'DUPLICATE_SHA_CONFLICT'):
                shadow_evaluate.v2_quality_metrics([a,b])

    def test_review_is_abstention_and_not_an_error_or_fake_match(self):
        report=shadow_evaluate.v2_quality_metrics([sample(prediction_action='REVIEW'),sample('b'*64,ground_truth_action='KEEP',prediction_action='DELETE')])
        synthetic=report['synthetic']
        self.assertEqual(synthetic['deferred_rate'],.5)
        self.assertEqual(synthetic['decided_errors'],1)
        self.assertEqual(synthetic['actions']['DELETE']['precision'],0)

    def test_low_confidence_or_abstention_cannot_count_as_automatic_action(self):
        report=shadow_evaluate.v2_quality_metrics([sample(confidence=.79),sample('b'*64,abstain=True)])
        self.assertEqual(report['synthetic']['deferred_rate'],1)
        self.assertEqual(report['synthetic']['actions']['DELETE']['proposed'],0)

    def test_synthetic_perfect_samples_never_satisfy_real_gate(self):
        rows=[sample(hashlib.sha256(str(n).encode()).hexdigest(),human_confirmed=True) for n in range(40)]
        report=shadow_evaluate.v2_quality_metrics(rows,remove_text_min_pass_rate=.95)
        self.assertEqual(report['synthetic']['actions']['DELETE']['precision'],1)
        self.assertEqual(report['real']['actions']['DELETE']['labeled'],0)
        self.assertFalse(report['statistical_gates_met']);self.assertFalse(report['release_authorized'])

    def real_sample(self,root,n,**changes):
        path=root/(str(n)+'.png');Image.new('RGB',(8,8),(n%256,n//256,10)).save(path)
        options=dict(evidence_kind='REAL_SHADOW',human_confirmed=True,label_source='unit-fixture-simulated-human-not-real-evidence',source_image=str(path));options.update(changes)
        return sample(hashlib.sha256(path.read_bytes()).hexdigest(),**options)

    def test_real_declared_samples_require_actual_matching_image_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);row=self.real_sample(root,1)
            report=shadow_evaluate.v2_quality_metrics([row])
            self.assertEqual(report['real']['actions']['DELETE']['labeled'],1)
            self.assertFalse(report['release_authorized'])
            with self.assertRaisesRegex(ValueError,'SOURCE_IMAGE_SHA'):
                shadow_evaluate.v2_quality_metrics([dict(row,image_sha256='0'*64)])
            with self.assertRaisesRegex(ValueError,'SOURCE_IMAGE_REQUIRED'):
                shadow_evaluate.v2_quality_metrics([{k:v for k,v in row.items() if k!='source_image'}])

    def test_box_directional_errors_and_unknown_are_not_absence(self):
        rows=[sample(ground_truth_retail_box='PRESENT',prediction_retail_box='ABSENT'),
              sample('b'*64,ground_truth_retail_box='ABSENT',prediction_retail_box='PRESENT'),
              sample('c'*64,ground_truth_retail_box='PRESENT',prediction_retail_box='UNKNOWN')]
        box=shadow_evaluate.v2_quality_metrics(rows)['synthetic']['retail_box']
        self.assertEqual(box['present_as_absent'],1);self.assertEqual(box['absent_as_present'],1)
        self.assertEqual(box['deferred'],1)
        self.assertEqual(box['present_as_absent_rate'],.5)
        self.assertEqual(box['absent_as_present_rate'],1)

    def test_sku_results_are_separate_for_with_and_without_box(self):
        rows=[sample(ground_truth_retail_box='PRESENT',sku_selection_correct=False),sample('b'*64,ground_truth_retail_box='ABSENT',sku_selection_correct=True)]
        sku=shadow_evaluate.v2_quality_metrics(rows)['synthetic']['sku_selection']
        self.assertEqual(sku['WITH_RETAIL_BOX']['accuracy'],0)
        self.assertEqual(sku['WITHOUT_RETAIL_BOX']['accuracy'],1)

    def test_missing_human_labels_and_severe_checks_never_pass_gates(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            rows=[self.real_sample(root,n,human_confirmed=False,severe_error=None) for n in range(30)]
            report=shadow_evaluate.v2_quality_metrics(rows)
            self.assertEqual(report['real']['actions']['DELETE']['labeled'],0)
            self.assertIsNone(report['real']['actions']['DELETE']['severe_error_rate'])
            self.assertFalse(report['gates']['DELETE']['met'])

    def test_gates_compute_statistics_but_never_grant_real_authorization(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);rows=[]
            for n in range(90):
                action=('DELETE','REMOVE_TEXT','AI_REGENERATE')[n//30]
                rows.append(self.real_sample(root,n,ground_truth_action=action,prediction_action=action,
                    ground_truth_retail_box='PRESENT' if n<30 else 'ABSENT',prediction_retail_box='PRESENT' if n<30 else 'ABSENT',repair_pass=True,sku_selection_correct=True))
            missing=shadow_evaluate.v2_quality_metrics(rows)
            self.assertFalse(missing['gates']['REMOVE_TEXT']['met'])
            report=shadow_evaluate.v2_quality_metrics(rows,remove_text_min_pass_rate=.95)
            self.assertTrue(report['statistical_gates_met'])
            self.assertFalse(report['release_authorized']);self.assertFalse(report['real_provenance_independently_verified'])
            damaged=copy.deepcopy(rows);damaged[0]['severe_error']=True
            self.assertFalse(shadow_evaluate.v2_quality_metrics(damaged,remove_text_min_pass_rate=.95)['gates']['DELETE']['met'])

    def test_invalid_or_excluded_fields_are_rejected(self):
        for changes in ({'image_type':'DESCRIPTION'},{'Description':'excluded'},{'confidence':float('nan')},{'severe_error':0},{'ground_truth_action':'REMOVE'},{'human_confirmed':True,'label_source':None}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):shadow_evaluate.v2_quality_metrics([sample(**changes)])


class RegistryAccuracyTests(unittest.TestCase):
    real_sample=V2AccuracyTests.real_sample
    # Test helpers use simulated labels; no fixture is production evidence.
    def registry(self,root,rows):
        samples=[]
        for row,truth,delete in rows:
            samples.append(dict(source_sha256=row['image_sha256'],source=row['source_image'],ground_truth={'third_party_watermark':truth},confirmations=[dict(label_status='USER_CONFIRMED_ACTION' if delete else 'USER_CONFIRMED',label_source='unit-fixture-simulated-human-not-real',ground_truth=dict(third_party_watermark=truth,whole_image_delete_requested=delete))]))
        path=root/'registry.json'
        path.write_text(json.dumps(dict(schema='deduplicated-confirmed-label-registry/v1.3',model_predictions_used_as_truth=False,samples=samples)),encoding='utf-8')
        return path

    def pending(self,root,n=1,**changes):
        options=dict(human_confirmed=False,ground_truth_action=None,ground_truth_retail_box=None,severe_error=None,repair_pass=None,sku_selection_correct=None)
        options.update(changes)
        return self.real_sample(root,n,**options)

    def test_registry_imports_only_explicit_action_without_mutating_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);row=self.pending(root);original=copy.deepcopy(row);path=self.registry(root,[(row,True,True)])
            report=shadow_evaluate.v2_quality_metrics([row],label_registry=path)
            self.assertEqual(row,original)
            self.assertEqual(report['real']['actions']['DELETE']['labeled'],1)
            self.assertEqual(report['real']['actions']['DELETE']['severe_unknown'],1)
            self.assertEqual(report['label_registry']['explicit_delete_labels'],1)
            self.assertFalse(report['gates']['DELETE']['met']);self.assertFalse(report['release_authorized'])

    def test_registry_binary_only_labels_never_become_keep_or_other_truth(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);row=self.pending(root,prediction_action='KEEP');path=self.registry(root,[(row,False,False)])
            report=shadow_evaluate.v2_quality_metrics([row],label_registry=path)
            self.assertEqual(report['label_registry']['binary_watermark_labels'],1)
            self.assertEqual(report['label_registry']['matched_real_binary_watermark_images'],1)
            self.assertEqual(report['label_registry']['explicit_delete_labels'],0)
            self.assertEqual(report['real']['actions']['KEEP']['labeled'],0)
            self.assertIsNone(report['real']['actions']['KEEP']['precision'])
            self.assertEqual(report['real']['retail_box']['unlabeled'],1)

    def test_registry_merges_complementary_same_sha_and_rejects_contradictions(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);row=self.pending(root)
            path=self.registry(root,[(row,True,False),(row,None,True)])
            report=shadow_evaluate.v2_quality_metrics([row,dict(row,image_type='DETAIL')],label_registry=path)
            self.assertEqual(report['label_registry']['unique_images'],1)
            self.assertEqual(report['label_registry']['matched_real_prediction_images'],1)
            self.assertEqual(report['real']['actions']['DELETE']['labeled'],1)
            path=self.registry(root,[(row,True,False),(row,False,False)])
            with self.assertRaisesRegex(ValueError,'REGISTRY_LABEL_CONFLICT'):
                shadow_evaluate.v2_quality_metrics([row],label_registry=path)

    def test_registry_detects_image_and_existing_truth_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);row=self.pending(root);path=self.registry(root,[(row,True,True)])
            with self.assertRaisesRegex(ValueError,'REGISTRY_ACTION_CONFLICT'):
                shadow_evaluate.v2_quality_metrics([dict(row,ground_truth_action='KEEP')],label_registry=path)
            Path(row['source_image']).write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'REGISTRY_IMAGE_SHA'):
                shadow_evaluate.v2_quality_metrics([row],label_registry=path)

    def test_registry_cannot_confirm_other_unreviewed_outcomes_or_fake_predictions(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);row=self.pending(root);path=self.registry(root,[(row,True,True)])
            with self.assertRaisesRegex(ValueError,'REGISTRY_UNCONFIRMED_OUTCOMES'):
                shadow_evaluate.v2_quality_metrics([dict(row,severe_error=False)],label_registry=path)
            report=shadow_evaluate.v2_quality_metrics([dict(row,evidence_kind='FAKE')],label_registry=path)
            self.assertEqual(report['real']['unique_images'],0)
            self.assertEqual(report['label_registry']['images_without_real_predictions'],1)
            self.assertFalse(report['statistical_gates_met'])

    def test_registry_cli_reports_missing_predictions_and_rejects_legacy_mode(self):
        import subprocess,sys
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);row=self.pending(root);path=self.registry(root,[(row,True,True)]);samples=root/'empty.jsonl';samples.write_text('',encoding='utf-8');output=root/'report.json'
            command=[sys.executable,shadow_evaluate.__file__,str(samples),'--label-registry',str(path),'--output',str(output)]
            result=subprocess.run(command+['--v2'],capture_output=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'))
            report=json.loads(output.read_text(encoding='utf-8'))
            self.assertEqual(report['status'],'NOT_EVALUATED')
            self.assertEqual(report['label_registry']['images_without_real_predictions'],1)
            self.assertIsNone(report['real']['actions']['DELETE']['precision'])
            result=subprocess.run(command,capture_output=True,timeout=30)
            self.assertNotEqual(result.returncode,0)


if __name__=='__main__':unittest.main()
