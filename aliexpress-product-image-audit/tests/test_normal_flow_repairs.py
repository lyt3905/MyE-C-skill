import tempfile,unittest,json
from pathlib import Path
from copy import deepcopy
from PIL import Image,ImageDraw
from candidate_quality import CandidateQualityGate
from remedy_planner import RemedyPlanner
from test_auto_remedy import Inspector
import test_full_audit_remediation_bridge as bridge
from full_product_audit import run_full_audit
from job_manager import JobManager,atomic_json
from automation_policy import AutomationPolicy
from test_auto_decision import CONFIG

class NormalFlowRepairTests(unittest.TestCase):
    def test_native_800_image_can_remove_edge_banner_without_upscaling(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'source.png';im=Image.new('RGB',(800,800),'white');ImageDraw.Draw(im).rectangle((200,200,600,600),fill='blue');im.save(p)
            item=dict(id='WM_MAIN_000',image_id='MAIN_000',pool='main',index=0,local=str(p),source_url='https://fake/a',evidence_ids=['WM_MAIN_000'])
            result=RemedyPlanner(d,CandidateQualityGate(Inspector()),allowed_actions={'CROP_BANNER'}).plan(item,[],{},crop_box=[0,40,800,800],subject_box=[200,200,601,601])
            self.assertIsNotNone(result);self.assertEqual(result['action'],'CROP_BANNER')
            with Image.open(Path(d)/result['candidate_asset']['path']) as image:self.assertEqual(image.size,(800,800))
    def test_confirmed_banner_can_be_planned_while_other_marks_stay_deferred(self):
        from auto_workflow import prepare
        with tempfile.TemporaryDirectory() as d:
            product,raw,reader,auditor,judge,template=bridge.FullAuditRemediationBridgeTests().fixture(d)
            for key,value in judge.results.items():
                if not key.startswith('WM_'):continue
                if key!=next(k for k in judge.results if k.startswith('WM_')):continue
                for row in value['results']:
                    row['marks'][0].update(classification='third_party_store_banner',owner='Known Toy Store',bbox_xyxy=[10,5,150,30])
                    row['marks'].append(dict(mark_id='M2',classification='unknown',owner='unknown',location='bottom',bbox_xyxy=[10,700,150,750],confidence=.4,abstain=True,evidence_ids=row['evidence_ids']))
            original_auditor=auditor
            def auditor(pid,shop,output_dir,site):
                result=original_auditor(pid,shop,output_dir,site)
                atomic_json(output_dir/'audit_account.json',{'account_fingerprint':site.account_fingerprint(),'status':'VERIFIED'})
                return result
            m=JobManager(Path(d)/'jobs');job=m.create(1,7,{'ai_requests':40,'full_resolution_images':32},mode='auto_apply')
            report=run_full_audit(m.root,1,7,reader,judge=judge,auditor=auditor,template_config=template,manager=m,job=job)
            job=m.load(report['job_id']);root=m.directory(job['job_id'])
            class CropInspector(Inspector):
                def inspect(self,source,candidate,context):
                    if (context.get('_image_repair') or {}).get('phase')=='POST_WRITE_READBACK':raise AssertionError('Byte-exact approved-candidate readback must not be reclassified')
                    return super().inspect(source,candidate,context)
                def propose(self,*args):raise AssertionError('Confirmed edge marks use their existing pixel regions')
            p=deepcopy(CONFIG);p['allow_actions']={'CROP_BANNER':True}
            result=prepare(root,job,AutomationPolicy(p),CandidateQualityGate(CropInspector()))
            self.assertEqual(result['status'],'AUTO_READY',result)
            self.assertGreater(result['deferred_count'],0)
            decisions=json.loads((root/'auto_decisions.json').read_text())['items']
            self.assertTrue(any(x['decision']=='AUTO_SAFE' and x['action']=='CROP_BANNER' for x in decisions))

            from workflow_runner import run_automatic
            from unittest.mock import patch
            from execution_ledger import ExecutionLedger
            blobs={r['url']:Path(r['file']).read_bytes() for r in raw};reader.saves=0;reader.uploads=0
            def upload(path):
                reader.uploads+=1;url='https://fake/upload';blobs[url]=Path(path).read_bytes();return url
            def save(pid,desired,**kwargs):reader.saves+=1;product.clear();product.update(deepcopy(desired))
            reader.upload=upload;reader.save=save;reader.fetch_image=lambda url:blobs[url];reader.readonly_client=lambda:reader
            with patch('execution_ledger.ExecutionLedger',side_effect=lambda:ExecutionLedger(Path(d)/'execution.sqlite')):
                checked=run_automatic(m,m.load(job['job_id']),AutomationPolicy(p),writer=reader,auditor=auditor,judge=judge,quality_gate=CandidateQualityGate(CropInspector()),full_audit_reader=reader)
            self.assertEqual(checked['status'],'PARTIALLY_AUTO_FIXED',checked)
            self.assertEqual((reader.uploads,reader.saves),(1,1))
            self.assertEqual(product['skus'][1]['skuImageUrl'],'https://fake/upload')

    def test_quality_judge_receives_the_authorized_local_repair_scope(self):
        from visual_quality import VisualQualityInspector
        from template_applicability import snapshot
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'source.png';Image.new('RGB',(800,800),'white').save(source)
            config=root/'templates.json';atomic_json(config,{'no_applicable_shop_ids':[7],'templates':[]});snapshot(config,root)
            class Judge:
                item=None
                def classify(self,task,item,context):
                    self.item=item
                    flags={k:True for k in ('product_identity_match','source_clean','candidate_visual_validation','protected_elements_preserved','residual_pass','subject_bounds_safe','model_match','packaging_match','official_source')}
                    return {'status':'CLEAN','results':[{'decision':'MATCH','confidence':.99,'abstain':False,'checks':flags}]*2}
            judge=Judge();inspector=VisualQualityInspector(root,{'shop_id':7,'templates_required':False},judge=judge,ocr_engine=lambda image:([],None))
            scope={'type':'CONFIRMED_MARK_REPAIR','action':'CROP_BANNER','boxes':[[10,0,100,30]],'phase':'PREPARE'}
            result=inspector.inspect(source,source,{'id':1,'_image_repair':scope,'descriptionJson':'never-send-description'})
            self.assertTrue(result['source_clean'])
            purpose=judge.item['purpose'];self.assertIn('CONFIRMED_MARK_REPAIR',purpose);self.assertIn('CROP_BANNER',purpose)
            self.assertNotIn('never-send-description',purpose)
