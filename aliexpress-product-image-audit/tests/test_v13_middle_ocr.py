import json
import tempfile
import unittest
import numpy as np

import audit_one
import test_v13_account_cli as cli


class MiddleOcrTests(unittest.TestCase):
    def image(self):
        image=np.full((800,800,3),255,np.uint8)
        image[450:480,250:530]=[0,0,255]
        return image

    def engine(self,image):
        red=(image[:,:,2]>240)&(image[:,:,0]<20)&(image[:,:,1]<20)
        if not red.any():return [],None
        ys,xs=np.where(red);box=[[int(xs.min()),int(ys.min())],[int(xs.max()+1),int(ys.min())],
                              [int(xs.max()+1),int(ys.max()+1)],[int(xs.min()),int(ys.max()+1)]]
        text='GenuineProductsStore' if image.shape[1]>800 else 'ductsStor'
        return [[box,text,.97]],None

    def test_middle_zoom_recovers_truncated_store_text_at_original_coordinates(self):
        items,hits,_=audit_one.run_ocr(self.engine,self.image())
        middle=[h for h in hits if h['region']=='middle28_x2']
        self.assertTrue(middle)
        self.assertEqual(middle[0]['text'],'GenuineProductsStore')
        self.assertTrue(all(abs(a-b)<=1 for a,b in zip(middle[0]['rect'],[250,450,530,480])))
        self.assertTrue(any(i['text']=='ductsStor' for i in items))

    def test_cached_middle_read_is_reclassified_and_official_print_stays_unflagged(self):
        item={'text':'GenuineProductsStore','score':.97,'rect':[250,450,530,480],'region':'middle28_x2'}
        items,hits,_=audit_one.classify_cached_ocr([item])
        self.assertEqual(items,[item]);self.assertEqual(len(hits),1)
        official=dict(item,text='TAKARA TOMY')
        _,hits,_=audit_one.classify_cached_ocr([official],title_text='TAKARA TOMY MPM-9')
        self.assertFalse(hits)

    def test_tiny_image_remains_decodable_by_all_ocr_passes(self):
        shapes=[]
        def empty(image):shapes.append(image.shape[:2]);return [],None
        audit_one.run_ocr(empty,np.zeros((2,1,3),np.uint8))
        self.assertEqual(len(shapes),4)
        self.assertTrue(all(h>0 and w>0 for h,w in shapes))

    def test_standard_cli_middle_ocr_reaches_machine_candidate_queue_without_writes(self):
        with tempfile.TemporaryDirectory() as root:
            writer,path,_,error=cli.AccountCliTests().execute(root,case='center_watermark',mode='audit')
            self.assertIsNone(error,repr(error))
            hits=json.loads((path/'audit_flags.json').read_text(encoding='utf-8'))['ocr_hits']
            self.assertTrue(any(r['kind']=='main' and r['region']=='middle28_x2' for r in hits))
            queue=json.loads((path/'ai_queue.json').read_text(encoding='utf-8'))['items']
            self.assertIn('WM_MAIN_000',[r['id'] for r in queue])
            self.assertEqual((writer.uploads,writer.saves),(0,0))
