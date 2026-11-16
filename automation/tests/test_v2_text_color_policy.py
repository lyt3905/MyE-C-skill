"""User policy: one color variant; unresolved text is retained, not erased."""
import copy
import unittest
from unittest.mock import patch
import test_v2_vision as vision
from test_v2_vision import observation
import test_v2_repairs_sku as sku_fixtures


def unknown_mark():
    return dict(kind='UNKNOWN_TEXT', owner='UNKNOWN', bbox=[.01,.8,.15,.9],
                confidence=.62, preserve_overlap_risk='LOW')


class TextColorPolicyTests(unittest.TestCase):
    setUp = vision.VisionTests.setUp
    client = vision.VisionTests.client
    decide = vision.VisionTests.decide

    def test_color_unknown_or_no_is_recorded_without_blocking_keep(self):
        def reply(model, item):
            row=observation(item)
            row['product_identity']['color_match']='UNKNOWN' if model==client.models[0] else 'NO'
            return row
        client, _=self.client(reply)
        result=self.decide(client)
        self.assertEqual(result['decision'],'KEEP')
        self.assertEqual([r['product_identity']['color_match'] for r in result['results']],['UNKNOWN'])

    def test_unknown_text_low_confidence_is_kept_without_fabricating_owner(self):
        fields=dict(visual_class=.9,product_identity=.9,box_relation=.9,watermark_ownership=.3,sku_suitability=.9)
        client, _=self.client(lambda m,i:observation(i,watermarks=[unknown_mark()],field_confidences=fields))
        result=self.decide(client)
        self.assertEqual(result['decision'],'KEEP')
        self.assertEqual(result['observation']['watermarks'][0],unknown_mark())
        self.assertEqual(result['observation']['field_confidences']['watermark_ownership'],.3)

    def test_creator_text_keeps_single_observation(self):
        def reply(model,item):
            mark=unknown_mark()
            if model==client.models[0]:mark.update(kind='CREATOR_CREDIT',owner='CREATOR',confidence=.9)
            return observation(item,watermarks=[mark])
        client, _=self.client(reply)
        result=self.decide(client)
        self.assertEqual(result['decision'],'KEEP')
        self.assertEqual({m['owner'] for m in result['observation']['watermarks']},{'CREATOR'})
        self.assertEqual(len(result['results']),1)

    def test_unknown_text_detected_by_one_model_only_is_kept(self):
        client, _=self.client(lambda m,i:observation(i,watermarks=[unknown_mark()] if m==client.models[0] else []))
        result=self.decide(client)
        self.assertEqual(result['decision'],'KEEP')
        self.assertEqual(result['observation']['watermarks'],[unknown_mark()])

    def test_uncertain_product_identity_is_record_only(self):
        client, _=self.client(lambda m,i:observation(i,product_identity=dict(same_product_as_context='UNKNOWN',structure_match='YES',model_visible='NO',color_match='UNKNOWN')))
        result=self.decide(client)
        self.assertEqual(result['decision'],'KEEP')
        self.assertEqual(result['observation']['product_identity']['same_product_as_context'],'UNKNOWN')

    def test_low_overall_confidence_is_not_raised(self):
        client, _=self.client(lambda m,i:observation(i,confidence=.79,watermarks=[unknown_mark()]))
        result=self.decide(client)
        self.assertEqual(result['decision'],'KEEP')
        self.assertEqual(result['observation']['confidence'],.79)

    def test_unknown_text_is_never_a_removal_target(self):
        from mye_c_automation.ai_judge.image_action_decision import validate
        with self.assertRaisesRegex(ValueError,'V2_NOT_REMOVABLE'):
            validate(observation(self.item,'REMOVE_TEXT',watermarks=[unknown_mark()]),self.item)

    def test_unknown_text_and_color_do_not_block_sku_selection(self):
        from mye_c_automation.sku_assignment import select_v2
        records=sku_fixtures.RepairSkuTests().records()
        for row in records:
            row['observation']['product_identity']['color_match']='UNKNOWN'
            row['observation']['watermarks']=[unknown_mark()]
        selection=select_v2({'skus':[dict(skuId='real',skuName='Without Box')]},records)
        self.assertEqual(len(selection['selected_sku_images']),2)
        self.assertEqual(selection['assignments'],{'real':'https://fake/0'})

    def test_known_store_watermark_still_not_sku_clean(self):
        from mye_c_automation.sku_assignment import select_v2
        records=sku_fixtures.RepairSkuTests().records()
        for row in records:
            mark=unknown_mark();mark.update(kind='STORE_WATERMARK',owner='THIRD_PARTY_STORE',confidence=.9)
            row['observation']['watermarks']=[mark]
        self.assertFalse(select_v2({'skus':[dict(skuId='real',skuName='Without Box')]},records)['selected_sku_images'])

    def test_fake_full_workflow_retains_unknown_text_and_original_bytes(self):
        import tempfile
        from mye_c_automation.ai_judge.image_action_decision import validate
        from test_v2_workflow import V2WorkflowTests
        def policy_observation(row,item):
            row=copy.deepcopy(row)
            row['product_identity']['color_match']='UNKNOWN'
            row['watermarks']=[unknown_mark()]
            return validate(row,item)
        # Fake model observations travel through the production coordinator,
        # SKU selection, save and independent content readback.
        with tempfile.TemporaryDirectory() as root,patch('mye_c_automation.ai_judge.image_action_decision.validate',side_effect=policy_observation):
            scenario=V2WorkflowTests.scenario(self,root,['KEEP','KEEP'])
            self.assertEqual(scenario['writer'].uploads,0)
            self.assertEqual(scenario['writer'].saves,1)
            self.assertTrue(scenario['result']['content_validation']['ok'])
            self.assertEqual(scenario['product']['images']['main'],scenario['original']['images']['main'])
            self.assertEqual(scenario['product']['descriptionJson'],scenario['original']['descriptionJson'])


if __name__=='__main__':unittest.main()
