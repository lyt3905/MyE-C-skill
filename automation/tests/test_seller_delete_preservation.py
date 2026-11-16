"""A valid explicit seller-poster DELETE must not become a local erasure."""
import copy,json,unittest
from pathlib import Path
from mye_c_automation.ai_judge.image_action_decision import apply_visual_rules,decide,reassess_seller_poster


class SellerDeletePreservationTests(unittest.TestCase):
    def observation(self):
        return json.loads((Path(__file__).parent/'fixtures/seller_poster_5185/observation.json').read_text(encoding='utf-8'))

    def resolve(self,row):
        class Replay:
            models=('deepseek-v4.1-flash',)
            def classify(self,*a,**kw):return dict(results=[copy.deepcopy(row)])
        return decide(Replay(),dict(id=row['item_id']),{'pid':5185})

    def test_real_5185_raw_delete_survives_both_program_gates(self):
        raw=self.observation();before=copy.deepcopy(raw)
        result=self.resolve(raw)
        self.assertEqual(result['decision'],'DELETE')
        self.assertEqual(result['observation']['decision'],'DELETE')
        self.assertEqual(result['reason_codes'],[])
        self.assertEqual(raw,before);self.assertEqual(result['results'],[before])
        self.assertFalse(any(r.get('decision') in {'REMOVE_TEXT','REVIEW'} for r in result['policy_adjustments']))

    def test_explicit_poster_delete_does_not_require_a_second_geometric_area_threshold(self):
        raw=self.observation()
        raw['watermarks']=[dict(kind='STORE_WATERMARK',owner='UNKNOWN',overlay_role='OTHER_STORE_FRAME',bbox=[0,0,.8,.01],confidence=0.,preserve_overlap_risk='LOW'),
            dict(kind='PROMOTIONAL_TEXT',owner='UNKNOWN',overlay_role='UNRESOLVED_TEXT',bbox=[.1,.4,.8,.5],confidence=0.,preserve_overlap_risk='LOW')]
        self.assertEqual(self.resolve(raw)['decision'],'DELETE')

    def test_abstention_uncertain_box_and_unknown_class_still_defer(self):
        for changes in ({'abstain':True},{'retail_box_status':'UNCERTAIN'},{'visual_class':'UNKNOWN'}):
            row=self.observation();row.update(changes)
            with self.subTest(changes=changes):self.assertEqual(self.resolve(row)['decision'],'REVIEW')

    def test_review_unknown_text_and_official_content_are_not_promoted(self):
        raw=self.observation();raw['decision']='REVIEW'
        adjusted,_=apply_visual_rules(raw);self.assertEqual(adjusted['decision'],'REVIEW')
        unknown=self.observation();unknown['watermarks']=[dict(kind='UNKNOWN_TEXT',owner='UNKNOWN',bbox=[0,0,.8,.1],confidence=.5,preserve_overlap_risk='LOW')]
        self.assertEqual(self.resolve(unknown)['decision'],'REVIEW')
        official=self.observation()
        for mark in official['watermarks']:mark['owner']='MANUFACTURER'
        official['decision']='REVIEW'
        self.assertEqual(self.resolve(official)['decision'],'REVIEW')
        # No new composite proof is inferred from protected manufacturer marks.
        from mye_c_automation.ai_judge.image_action_decision import is_seller_promotional_composite
        self.assertFalse(is_seller_promotional_composite(official))

    def test_useful_photo_small_badge_keeps_existing_nondelete_handling(self):
        row=self.observation();row['visual_class']='TOY_PRODUCT'
        row['watermarks']=[dict(kind='STORE_WATERMARK',owner='UNKNOWN',overlay_role='OTHER_STORE_FRAME',bbox=[0,0,.1,.03],confidence=.9,preserve_overlap_risk='LOW')]
        self.assertEqual(self.resolve(row)['decision'],'REMOVE_TEXT')

    def test_existing_archived_program_error_can_be_reassessed_without_mutating_it(self):
        old=dict(decision='REVIEW',reason_codes=['TEXT_OWNERSHIP_UNRESOLVED'],models=['deepseek-v4.1-flash'],results=[self.observation()],observation=None)
        before=copy.deepcopy(old);result=reassess_seller_poster(old)
        self.assertEqual(result['decision'],'DELETE');self.assertEqual(old,before)
        self.assertEqual(result['results'],before['results'])
