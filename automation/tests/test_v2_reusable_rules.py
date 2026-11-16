"""Repeatable regressions for the user corrections from PID4086/PID5085."""
import copy,hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import test_v2_vision as vision
import test_v2_workflow as workflow
from test_v2_vision import observation


class RuleTests(unittest.TestCase):
    setUp=vision.VisionTests.setUp
    client=vision.VisionTests.client
    decide=vision.VisionTests.decide
    def test_box_identity_only_does_not_block_keep(self):
        client,_=self.client(lambda m,i:observation(i,box_relation='POSSIBLY_SAME_PRODUCT'))
        self.assertEqual(self.decide(client)['decision'],'KEEP')

    def test_store_frame_is_deleted_without_mutating_raw_keep(self):
        mark=dict(kind='STORE_WATERMARK',owner='UNKNOWN',bbox=[0,.85,1,1],confidence=0.,preserve_overlap_risk='LOW',overlay_role='OTHER_STORE_FRAME')
        client,_=self.client(lambda m,i:observation(i,visual_class='DECORATED_COMPOSITE',watermarks=[mark]))
        result=self.decide(client)
        self.assertEqual(result['decision'],'DELETE')
        self.assertEqual(result['results'][0]['decision'],'KEEP')
        self.assertEqual(result['results'][0]['watermarks'][0]['owner'],'UNKNOWN')

    def test_explicit_added_watermark_unknown_owner_enters_local_repair(self):
        mark=dict(kind='UNKNOWN_TEXT',owner='UNKNOWN',bbox=[.01,.85,.2,.95],confidence=0.,preserve_overlap_risk='LOW',overlay_role='ADDED_WATERMARK')
        client,_=self.client(lambda m,i:observation(i,watermarks=[mark]))
        self.assertEqual(self.decide(client)['decision'],'REMOVE_TEXT')

    def test_manufacturer_or_creator_is_protected_even_with_bad_overlay_label(self):
        for owner in ('MANUFACTURER','CREATOR','PRODUCT','PACKAGING'):
            with self.subTest(owner=owner):
                mark=dict(kind='PRODUCT_PRINT',owner=owner,bbox=[0,.8,.3,1],confidence=0.,preserve_overlap_risk='LOW',overlay_role='ADDED_WATERMARK')
                client,_=self.client(lambda m,i:observation(i,watermarks=[mark]))
                client.result_cache.root=self.root/owner
                client.result_cache.root.mkdir(exist_ok=True)
                self.assertEqual(self.decide(client)['decision'],'KEEP')

    def test_useful_size_chart_without_seller_notice_role_stays_keep(self):
        client,_=self.client(lambda m,i:observation(i,visual_class='SIZE_CHART',toy_present=False))
        self.assertEqual(self.decide(client)['decision'],'KEEP')

    def test_protected_print_kind_cannot_be_overridden_by_unknown_owner_and_overlay_role(self):
        from mye_c_automation.ai_judge.image_action_decision import mark_disposition
        for kind in ('MANUFACTURER_LOGO','PRODUCT_PRINT','PACKAGING_PRINT','MODEL_TEXT','CREATOR_CREDIT','NORMAL_PHOTO_TEXT'):
            mark=dict(kind=kind,owner='UNKNOWN',overlay_role='ADDED_WATERMARK',confidence=0.,bbox=[0,.8,1,1],preserve_overlap_risk='LOW')
            with self.subTest(kind=kind):self.assertEqual(mark_disposition(mark),'PROTECTED')

    def test_box_relation_is_record_only_for_sku_selection_too(self):
        from mye_c_automation.sku_assignment import select_v2
        box=observation(self.item,visual_class='TOY_WITH_RETAIL_BOX',retail_box_status='PRESENT',retail_box_bbox=[0,0,1,1],box_relation='POSSIBLY_SAME_PRODUCT')
        box['sku_suitability'].update(is_retail_box_photo=True,recommended_group='WITH_RETAIL_BOX')
        record=dict(sha256='a'*64,url='https://fake/box',image_id='BOX',width=800,height=800,decision='KEEP',observation=box)
        p=dict(skus=[dict(skuId='1',skuName='With Retail Box',skuImageUrl='https://fake/box')])
        self.assertEqual(select_v2(p,[record])['sku_packaging_decision'],'WITH_RETAIL_BOX')

    def test_explicit_whole_frame_notice_unknown_owner_is_deleted(self):
        mark=dict(kind='UNKNOWN_TEXT',owner='UNKNOWN',bbox=[0,0,1,1],confidence=0.,preserve_overlap_risk='LOW',overlay_role='SELLER_NOTICE')
        client,_=self.client(lambda m,i:observation(i,visual_class='OTHER',toy_present=False,watermarks=[mark]))
        self.assertEqual(self.decide(client)['decision'],'DELETE')


class WorkflowTests(unittest.TestCase):
    def scenario(self,root,actions,**kwargs):return workflow.V2WorkflowTests.scenario(self,root,actions,**kwargs)

    @staticmethod
    def body(p,assets,urls):
        alias='https://fake/body-alias';assets[alias]=assets[urls[0]]
        p['descriptionJson']=json.dumps([{'type':'text','texts':[{'content':'KEEP THIS COPY'}]},
            {'type':'image','url':alias,'style':{'width':800}},
            {'type':'image','url':urls[-1]},
            {'type':'text','shopFooter':True,'texts':[{'content':'KEEP FOOTER'}]},
            {'type':'image','url':'https://must-not-download/footer'}])

    def test_delete_all_aliases_and_body_in_one_formal_save(self):
        with tempfile.TemporaryDirectory() as root:
            s=self.scenario(root,['DELETE','KEEP'],product_transform=self.body)
            self.assertEqual(s['writer'].saves,1)
            nodes=json.loads(s['product']['descriptionJson'])
            self.assertEqual(nodes,[json.loads(s['original']['descriptionJson'])[i] for i in (0,2,3,4)])
            self.assertTrue(s['result']['content_validation']['ok'])

    def test_repair_all_aliases_body_and_pools_one_upload(self):
        with tempfile.TemporaryDirectory() as root:
            s=self.scenario(root,['REMOVE_TEXT','KEEP'],product_transform=self.body)
            self.assertEqual(s['writer'].uploads,1);self.assertEqual(s['writer'].saves,1)
            self.assertEqual(json.loads(s['product']['descriptionJson'])[1]['url'],s['product']['images']['main'][0])
            self.assertTrue(s['result']['content_validation']['ok'])

    def test_body_only_image_is_audited_and_deleted(self):
        def transform(p,a,u):
            self.body(p,a,u)
            for pool in ('main','detail'):p['images'][pool].remove(u[0])
        with tempfile.TemporaryDirectory() as root:
            s=self.scenario(root,['DELETE','KEEP'],product_transform=transform)
            self.assertEqual(s['calls'].count('image_action_decision'),2)
            self.assertEqual(s['writer'].saves,1)
            self.assertNotIn('body-alias',s['product']['descriptionJson'])

    def test_body_only_repair_is_uploaded_without_fabricating_pool_slot(self):
        def transform(p,a,u):
            self.body(p,a,u)
            for pool in ('main','detail'):p['images'][pool].remove(u[0])
        with tempfile.TemporaryDirectory() as root:
            s=self.scenario(root,['REMOVE_TEXT','KEEP'],product_transform=transform)
            self.assertEqual(s['writer'].uploads,1);self.assertEqual(s['writer'].saves,1)
            self.assertEqual(len(s['product']['images']['main']),1)
            self.assertIn('upload',json.loads(s['product']['descriptionJson'])[1]['url'])

    def test_description_transport_scope_is_used_by_formal_executor(self):
        from mye_c_automation.executor.site_write_client import SiteWriteClient
        from mye_c_automation.site_client import _SiteTransport
        from mye_c_automation.workflow_runner import run_automatic
        sent=[]
        def wire(manager,job,policy,**kwargs):
            original=kwargs['writer'];site=_SiteTransport.__new__(_SiteTransport)
            site.product=original.product;site.current_shop=original.current_shop
            site.account_fingerprint=original.account_fingerprint
            site.upload=original.upload;site.fetch_image=original.fetch_image
            def call(path,data=None,method=None):
                sent.append(copy.deepcopy(data));desired=original.product(job['pid']);desired.update(data)
                original.save(job['pid'],desired);return {'data':desired}
            site.call=call
            adapter=SiteWriteClient(site);adapter.fetch_image=original.fetch_image
            kwargs['writer']=adapter
            return run_automatic(manager,job,policy,**kwargs)
        with tempfile.TemporaryDirectory() as root,patch('test_v2_workflow.run_automatic',side_effect=wire):
            s=self.scenario(root,['REMOVE_TEXT','KEEP'],product_transform=self.body)
            self.assertEqual(len(sent),1);self.assertTrue(s['result']['content_validation']['ok'])
            self.assertIn('upload',sent[0]['descriptionJson'])

    def test_footer_same_url_as_deleted_body_image_still_preserved(self):
        def transform(p,a,u):
            self.body(p,a,u);nodes=json.loads(p['descriptionJson']);nodes[-1]['url']=nodes[1]['url'];p['descriptionJson']=json.dumps(nodes)
        with tempfile.TemporaryDirectory() as root:
            s=self.scenario(root,['DELETE','KEEP'],product_transform=transform)
            self.assertEqual(json.loads(s['product']['descriptionJson'])[-1],json.loads(s['original']['descriptionJson'])[-1])
            self.assertTrue(s['result']['content_validation']['ok'])

    def test_product_text_image_block_before_marked_footer_is_audited(self):
        def transform(p,a,u):
            self.body(p,a,u);nodes=json.loads(p['descriptionJson'])
            nodes[1]={'type':'text-image','texts':[{'content':'Original mixed copy'}],'images':[{'url':nodes[1]['url'],'style':{'width':800}}]}
            p['descriptionJson']=json.dumps(nodes)
        with tempfile.TemporaryDirectory() as root:
            s=self.scenario(root,['REMOVE_TEXT','KEEP'],product_transform=transform)
            node=json.loads(s['product']['descriptionJson'])[1]
            self.assertEqual(node['texts'],[{'content':'Original mixed copy'}])
            self.assertIn('upload',node['images'][0]['url'])
            self.assertTrue(s['result']['content_validation']['ok'])

    def test_unreadable_body_image_is_reported_unreviewed_not_passed(self):
        def transform(p,a,u):
            self.body(p,a,u);a.pop('https://fake/body-alias')
        with tempfile.TemporaryDirectory() as root:
            s=self.scenario(root,['KEEP','KEEP'],product_transform=transform)
            report=json.loads((s['root']/'full_audit_report.json').read_text())
            self.assertEqual(report['audit_status'],'INCOMPLETE')
            self.assertTrue(any(r['target_type']=='description_image' and r['decision']=='REVIEW' for r in report['occurrences']))
            self.assertNotEqual(s['result']['status'],'AUTO_VERIFIED')

    def test_retained_pool_does_not_mask_body_only_readback_failure(self):
        def transform(p,a,u):
            self.body(p,a,u)
        from mye_c_automation.v2_remediation import verify_content
        for corruption in ('text','footer','stale_alias'):
            with self.subTest(corruption=corruption),tempfile.TemporaryDirectory() as root:
                s=self.scenario(root,['REMOVE_TEXT','KEEP'],product_transform=transform)
                plan=json.loads((s['root']/'plan.v2.json').read_text())
                after=copy.deepcopy(s['product']);nodes=json.loads(after['descriptionJson'])
                if corruption=='text':nodes[0]['texts'][0]['content']='CORRUPTED'
                elif corruption=='footer':nodes[-1]['url']='https://fake/changed-footer'
                else:nodes[1]['url']='https://fake/body-alias'
                after['descriptionJson']=json.dumps(nodes)
                with patch.object(s['writer'],'product',return_value=after):self.assertFalse(verify_content(s['root'],plan,s['writer'])['ok'])


class FrozenCorrections(unittest.TestCase):
    def test_eight_historical_samples_follow_human_annotations_without_rewriting_raw(self):
        from mye_c_automation.ai_judge.image_action_decision import apply_visual_rules, mark_disposition
        folder=Path(__file__).parent/'fixtures/v2_image_corrections';fixture=json.loads((folder/'labels.json').read_text(encoding='utf-8'))
        self.assertEqual(len(fixture['rows']),8)
        for row in fixture['rows']:
            with self.subTest(sample=row['id']):
                self.assertEqual(hashlib.sha256((folder/row['file']).read_bytes()).hexdigest(),row['sha256'])
                raw=copy.deepcopy(row['raw_observation']);annotated=copy.deepcopy(raw)
                marks=[m for m in annotated['watermarks'] if mark_disposition(m)!='PROTECTED']
                if not marks:
                    mark=dict(kind='PROMOTIONAL_TEXT',bbox=[0,0,1,1],owner='UNKNOWN',confidence=0.,preserve_overlap_risk='LOW');annotated['watermarks'].append(mark)
                else:mark=marks[0]
                mark['overlay_role']=row['role']
                if row.get('repair_mode'):mark['repair_mode']=row['repair_mode']
                corrected,_=apply_visual_rules(annotated)
                self.assertEqual(corrected['decision'],row['expected'])
                self.assertEqual(raw,row['raw_observation'])

    def test_background_glyph_mask_keeps_alpha_and_outside_pixels(self):
        import numpy as np
        from PIL import Image,ImageDraw
        from mye_c_automation.image_repairs_v2 import remove_text, deterministic_quality
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);im=Image.new('RGBA',(800,800),'white');d=ImageDraw.Draw(im);d.rectangle((300,100,500,700),fill=(50,20,100,255));d.text((20,740),'WATERMARK',fill=(245,245,245,255));d.rectangle((0,0,8,799),fill=(0,0,0,0));p=root/'source.png';im.save(p)
            mark=dict(kind='UNKNOWN_TEXT',owner='UNKNOWN',bbox=[.01,.9,.3,.98],confidence=0.,preserve_overlap_risk='HIGH',overlay_role='ADDED_WATERMARK',repair_mode='BACKGROUND_GLYPHS')
            result=remove_text(p,dict(watermarks=[mark],preserve_regions=[],background_complexity='SMOOTH'),root/'out',rights='OWNED_OR_LICENSED',algorithm='OPENCV_TELEA')
            self.assertTrue(deterministic_quality(p,result['output_path'],result['mask_path'])['ok'])
            self.assertTrue(np.array_equal(np.array(im.getchannel('A')),np.array(Image.open(result['output_path']).getchannel('A'))))

    def test_foreground_scope_does_not_protect_empty_background_inside_coarse_box(self):
        import numpy as np
        from mye_c_automation.image_repairs_v2 import mask_for
        image=np.full((100,100,3),255,np.uint8);image[40:60,40:60]=[40,20,100];image[45:49,15:30]=245
        mark=dict(kind='UNKNOWN_TEXT',owner='UNKNOWN',bbox=[.1,.4,.7,.6],confidence=0.,preserve_overlap_risk='HIGH',overlay_role='ADDED_WATERMARK',repair_mode='BACKGROUND_GLYPHS')
        obs=dict(toy_present=True,retail_box_status='ABSENT',background_complexity='SMOOTH',watermarks=[mark],preserve_regions=[dict(kind='whole toy bounding box',scope='PRODUCT_FOREGROUND',bbox=[0,0,1,1])])
        mask,_=mask_for((100,100),obs,image=image,dilation=0)
        self.assertTrue(mask[46,20]>0);self.assertFalse(mask[50,50])
        exact=copy.deepcopy(obs);exact['preserve_regions'][0]['scope']='EXACT_REGION'
        with self.assertRaises(ValueError):mask_for((100,100),exact,image=image,dilation=0)


if __name__=='__main__':unittest.main()
