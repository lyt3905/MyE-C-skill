"""Unknown text ownership must not block deleting a valueless text-only image."""
import tempfile
import unittest
from unittest.mock import patch
import test_v2_vision as vision
import test_v2_workflow as workflow


def text_notice(item,decision='DELETE',**changes):
    row=vision.observation(item,decision,**changes)
    row.update(visual_class='TEXT_WATERMARK',toy_present=False,retail_box_status='ABSENT',subject_complete=False,
               watermarks=[dict(kind='PROMOTIONAL_TEXT',owner='UNKNOWN',bbox=[.02,.1,.98,.9],confidence=.5,preserve_overlap_risk='LOW')])
    return row


class PureTextDeletionTests(unittest.TestCase):
    setUp=vision.VisionTests.setUp
    client=vision.VisionTests.client
    decide=vision.VisionTests.decide

    def test_explicit_delete_for_pure_text_image_does_not_need_owner(self):
        client,calls=self.client(lambda m,i:text_notice(i))
        result=self.decide(client)
        self.assertEqual(result['decision'],'DELETE')
        self.assertFalse(result['reason_codes'])
        self.assertEqual(result['observation']['watermarks'][0]['owner'],'UNKNOWN')
        self.assertEqual(len(calls),1)

    def test_unknown_text_does_not_authorize_deleting_a_product_photo(self):
        def photo(model,item):
            row=text_notice(item);row.update(visual_class='TOY_PRODUCT',toy_present=True)
            return row
        client,_=self.client(photo)
        result=self.decide(client)
        self.assertEqual(result['decision'],'REVIEW')
        self.assertIn('TEXT_OWNERSHIP_UNRESOLVED',result['reason_codes'])

    def test_pure_text_keep_is_not_silently_changed_to_delete(self):
        client,_=self.client(lambda m,i:text_notice(i,'KEEP'))
        self.assertEqual(self.decide(client)['decision'],'KEEP')

    def test_box_uncertainty_and_explicit_abstention_are_not_waived(self):
        for option in ('box','abstain'):
            with self.subTest(option=option):
                def reply(model,item):
                    row=text_notice(item)
                    if option=='box':row['retail_box_status']='UNCERTAIN'
                    else:row['abstain']=True
                    return row
                client,_=self.client(reply)
                client.cache=self.root/option;client.cache.mkdir();client.result_cache.root=client.cache
                self.assertEqual(self.decide(client)['decision'],'REVIEW')

    def test_fake_delete_reaches_save_and_independent_readback(self):
        def reply(item,decision='KEEP',**changes):
            return text_notice(item,decision,**changes) if decision=='DELETE' else vision.observation(item,decision,**changes)
        with tempfile.TemporaryDirectory() as root,patch('test_v2_workflow.observation',side_effect=reply):
            s=workflow.V2WorkflowTests.scenario(self,root,['DELETE','KEEP'])
            deleted=s['original']['images']['main'][0]
            self.assertEqual(s['writer'].saves,1)
            self.assertEqual(s['writer'].uploads,0)
            self.assertNotIn(deleted,s['product']['images']['main'])
            self.assertNotIn(deleted,s['product']['images']['detail'])
            self.assertTrue(s['result']['content_validation']['ok'])
            self.assertEqual(s['product']['descriptionJson'],s['original']['descriptionJson'])


if __name__=='__main__':unittest.main()
