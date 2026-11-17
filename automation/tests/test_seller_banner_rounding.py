import copy,unittest
from test_seller_header_footer import poster
from mye_c_automation.ai_judge.image_action_decision import apply_visual_rules,is_large_promotional_frame,reassess_seller_poster

class SellerBannerRoundingTests(unittest.TestCase):
    def observation(self):
        row=poster()
        row['watermarks']=[dict(kind='PROMOTIONAL_TEXT',bbox=[.02,.88,.4,.98],confidence=.99,preserve_overlap_risk='LOW',owner='UNKNOWN',overlay_role='SELLER_NOTICE'),dict(kind='STORE_WATERMARK',bbox=[.5,.92,.93,.98],confidence=.99,preserve_overlap_risk='LOW',owner='UNKNOWN',overlay_role='OTHER_STORE_FRAME'),dict(kind='STORE_WATERMARK',bbox=[.42,.36,.64,.55],confidence=.55,preserve_overlap_risk='MEDIUM',owner='UNKNOWN',overlay_role='ADDED_WATERMARK')]
        return row
    def test_exact_tenth_height_does_not_fall_below_threshold_due_to_binary_roundoff(self):
        row=self.observation();before=copy.deepcopy(row)
        self.assertTrue(is_large_promotional_frame(row));self.assertEqual(apply_visual_rules(row)[0]['decision'],'DELETE');self.assertEqual(row,before)
    def test_materially_shorter_banner_does_not_gain_large_frame_proof(self):
        row=self.observation();row['watermarks'][0]['bbox'][1]=.881
        self.assertFalse(is_large_promotional_frame(row))
    def test_reassessment_keeps_original_delete_and_preserves_old_program_record(self):
        raw=self.observation();old=dict(decision='REVIEW',observation=dict(raw,decision='REVIEW'),results=[raw],models=['deepseek-v4.1-flash'],policy_adjustments=[],reason_codes=['TEXT_OWNERSHIP_UNRESOLVED']);before=copy.deepcopy(old)
        self.assertEqual(reassess_seller_poster(old)['decision'],'DELETE');self.assertEqual(old,before)
    def test_raw_review_and_protected_marks_are_not_promoted(self):
        row=self.observation();row['decision']='REVIEW';self.assertEqual(apply_visual_rules(row)[0]['decision'],'REVIEW')
        for m in row['watermarks']:m['owner']='MANUFACTURER'
        self.assertFalse(is_large_promotional_frame(row))
