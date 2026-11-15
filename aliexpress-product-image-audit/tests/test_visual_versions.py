"""Same-photo version matching must reject another pose of the same product."""
import copy,hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from test_v2_vision import observation
import test_v2_workflow as workflow
import test_v2_reusable_rules as reusable

FIXTURE=Path(__file__).parent/'fixtures/visual_versions'


def overlay():
    return dict(kind='STORE_WATERMARK',owner='UNKNOWN',overlay_role='ADDED_WATERMARK',confidence=0.,preserve_overlap_risk='LOW',bbox=[0,.85,1,1])


class VisualVersionTests(unittest.TestCase):
    def test_real_framed_and_clean_are_same_photo(self):
        from visual_versions import compare_versions
        o=dict(watermarks=[overlay(),dict(overlay(),bbox=[0,0,.25,.15]),dict(overlay(),bbox=[.75,0,1,.18])])
        result=compare_versions(FIXTURE/'framed.bin',FIXTURE/'clean.bin',o)
        self.assertTrue(result['verified'],result)
        self.assertGreater(result['inliers'],30)

    def test_same_product_background_but_different_pose_is_not_same_photo(self):
        from visual_versions import compare_versions
        result=compare_versions(FIXTURE/'framed.bin',FIXTURE/'different-pose.bin',dict(watermarks=[overlay()]))
        self.assertFalse(result['verified'],result)

    def test_resized_compressed_same_photo_matches(self):
        from PIL import Image
        from visual_versions import compare_versions
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'compressed.jpg'
            with Image.open(FIXTURE/'clean.bin') as image:
                image.resize((900,900)).convert('RGB').save(path,quality=85)
            o=dict(watermarks=[overlay(),dict(overlay(),bbox=[0,0,.25,.15]),dict(overlay(),bbox=[.75,0,1,.18])])
            self.assertTrue(compare_versions(FIXTURE/'framed.bin',path,o)['verified'])

    def test_dirty_unknown_review_and_small_candidates_are_ineligible(self):
        from visual_versions import clean_candidate
        item=dict(id='x',sha256='a'*64,image_type='MAIN',evidence_ids=['source'])
        result=dict(decision='KEEP',observation=observation(item))
        content=dict(width=1000,height=1000,format='JPEG')
        self.assertTrue(clean_candidate(result,content))
        for update in (dict(watermarks=[overlay()]),dict(visual_class='UNKNOWN'),dict(retail_box_status='UNCERTAIN'),dict(abstain=True),dict(watermarks=[dict(overlay(),kind='UNKNOWN_TEXT',overlay_role='UNRESOLVED_TEXT')])):
            bad=copy.deepcopy(result);bad['observation'].update(update)
            self.assertFalse(clean_candidate(bad,content),update)
        self.assertFalse(clean_candidate(dict(result,decision='REVIEW'),content))
        self.assertFalse(clean_candidate(result,dict(content,width=799)))

    def test_small_store_frame_raw_delete_uses_local_repair_fallback(self):
        from ai_judge.image_action_decision import apply_visual_rules
        item=dict(id='x',sha256='a'*64,image_type='MAIN',evidence_ids=['source'])
        o=observation(item,'DELETE',watermarks=[dict(overlay(),bbox=[0,0,.2,.1],overlay_role='OTHER_STORE_FRAME')])
        normalized,adjustments=apply_visual_rules(o)
        self.assertEqual(normalized['decision'],'REMOVE_TEXT')
        self.assertEqual(o['decision'],'DELETE')
        self.assertTrue(adjustments)

    def test_composed_top_badges_and_bottom_promo_band_are_large_frame(self):
        from ai_judge.image_action_decision import is_large_promotional_frame
        marks=[dict(overlay(),bbox=[0,0,.18,.12]),dict(overlay(),kind='PROMOTIONAL_TEXT',bbox=[.79,0,.99,.11]),dict(overlay(),kind='PROMOTIONAL_TEXT',bbox=[0,.875,.47,1]),dict(overlay(),kind='PROMOTIONAL_TEXT',bbox=[.47,.875,1,1])]
        self.assertTrue(is_large_promotional_frame(dict(watermarks=marks)))
        self.assertFalse(is_large_promotional_frame(dict(watermarks=[dict(overlay(),bbox=[.85,.85,.98,.95])])) )
        self.assertFalse(is_large_promotional_frame(dict(watermarks=[dict(m,owner='MANUFACTURER') for m in marks])))


def framed_observation(result,item):
    if item['sha256']==hashlib.sha256((FIXTURE/'framed.bin').read_bytes()).hexdigest():
        result['watermarks']=[dict(overlay(),bbox=[0,0,.18,.12]),dict(overlay(),kind='PROMOTIONAL_TEXT',bbox=[.79,0,.99,.11]),dict(overlay(),kind='PROMOTIONAL_TEXT',bbox=[0,.875,1,1])]
    return result


class VersionWorkflowTests(unittest.TestCase):
    def test_existing_clean_version_also_precedes_regeneration(self):
        with tempfile.TemporaryDirectory() as root,patch('image_repairs_v2.remove_text',side_effect=AssertionError('replacement first')):
            s=workflow.V2WorkflowTests.scenario(self,root,['AI_REGENERATE','KEEP'],asset_images={0:FIXTURE/'framed.bin',1:FIXTURE/'clean.bin'},observation_transform=framed_observation)
            self.assertEqual(s['product']['images']['main'][0],'https://fake/1')
            self.assertEqual(s['writer'].uploads,0);self.assertEqual(s['writer'].saves,1)
            self.assertNotIn('image_quality_v2',s['calls'])

    def scenario(self,root,candidate='clean',transform=None,**kwargs):
        return workflow.V2WorkflowTests.scenario(self,root,['REMOVE_TEXT','KEEP'],asset_images={0:FIXTURE/'framed.bin',1:FIXTURE/(candidate+'.bin')},observation_transform=framed_observation,product_transform=transform,**kwargs)

    def test_verified_clean_version_replaces_before_delete_or_inpaint(self):
        with tempfile.TemporaryDirectory() as root,patch('image_repairs_v2.remove_text',side_effect=AssertionError('replacement must precede repair')):
            s=self.scenario(root,transform=reusable.WorkflowTests.body)
            self.assertEqual(s['writer'].saves,1);self.assertEqual(s['writer'].uploads,0)
            self.assertEqual(s['product']['images']['main'][0],'https://fake/1')
            self.assertEqual(json.loads(s['product']['descriptionJson'])[1]['url'],'https://fake/1')
            decisions=json.loads((s['root']/'auto_decisions.json').read_text())['items']
            self.assertTrue(any(r['action']=='REPLACE_TWIN' and r['decision']=='AUTO_SAFE' for r in decisions))
            self.assertNotIn('image_quality_v2',s['calls'])
            self.assertTrue(s['result']['content_validation']['ok'])

    def test_no_clean_version_large_frame_is_deleted(self):
        with tempfile.TemporaryDirectory() as root,patch('image_repairs_v2.remove_text',side_effect=AssertionError('large frame should be deleted')):
            s=self.scenario(root,candidate='different-pose')
            self.assertEqual(s['writer'].saves,1);self.assertEqual(s['writer'].uploads,0)
            self.assertEqual(s['product']['images']['main'],['https://fake/1'])

    def test_no_clean_version_small_overlay_is_locally_repaired(self):
        with tempfile.TemporaryDirectory() as root:
            s=workflow.V2WorkflowTests.scenario(self,root,['REMOVE_TEXT','KEEP'])
            self.assertEqual(s['writer'].uploads,1);self.assertEqual(s['writer'].saves,1)
            self.assertTrue(s['result']['content_validation']['ok'])

    def test_sku_reference_only_uses_clean_version(self):
        with tempfile.TemporaryDirectory() as root:
            s=self.scenario(root,reference_only=True)
            self.assertEqual(s['writer'].uploads,0);self.assertEqual(s['writer'].saves,1)
            self.assertEqual(s['product']['skus'][0]['skuImageUrl'],'https://fake/1')
            self.assertTrue(s['result']['content_validation']['ok'])

    def test_shared_main_detail_body_sku_references_are_replaced(self):
        with tempfile.TemporaryDirectory() as root:
            s=self.scenario(root,transform=reusable.WorkflowTests.body,sku_on_first=True)
            for pool in ('main','detail','sku'):
                self.assertNotIn('https://fake/0',s['product']['images'][pool])
            self.assertEqual(s['product']['skus'][0]['skuImageUrl'],'https://fake/1')
            self.assertTrue(s['result']['content_validation']['ok'])
            self.assertEqual(s['writer'].uploads,0);self.assertEqual(s['writer'].saves,1)

    def test_replacement_readback_failure_is_not_success(self):
        with tempfile.TemporaryDirectory() as root:
            s=self.scenario(root,corrupt_readback='retained_bytes')
            self.assertFalse(s['result']['content_validation']['ok'])
            self.assertNotEqual(s['result']['status'],'AUTO_VERIFIED')

    def test_body_only_existing_clean_version_can_replace(self):
        def body_only(p,a,u):
            reusable.WorkflowTests.body(p,a,u)
            for pool in ('main','detail'):p['images'][pool].remove(u[0])
        with tempfile.TemporaryDirectory() as root:
            s=self.scenario(root,transform=body_only)
            self.assertEqual(s['writer'].uploads,0);self.assertEqual(s['writer'].saves,1)
            self.assertEqual(json.loads(s['product']['descriptionJson'])[1]['url'],'https://fake/1')
            self.assertTrue(s['result']['content_validation']['ok'])


if __name__=='__main__':unittest.main()
