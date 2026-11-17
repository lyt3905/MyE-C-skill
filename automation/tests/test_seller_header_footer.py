import copy,hashlib,json,tempfile,unittest
from pathlib import Path
from test_v2_vision import observation

def poster():
    return observation(dict(id='A',sha256='a'*64,image_type='DETAIL',evidence_ids=['A']),decision='DELETE',visual_class='DECORATED_COMPOSITE',watermarks=[
        dict(kind='STORE_WATERMARK',bbox=[.33,0,.72,.04],confidence=.95,preserve_overlap_risk='LOW',owner='UNKNOWN',overlay_role='OTHER_STORE_FRAME'),
        dict(kind='PROMOTIONAL_TEXT',bbox=[0,.86,.2,.94],confidence=.9,preserve_overlap_risk='MEDIUM',owner='UNKNOWN',overlay_role='SELLER_NOTICE'),
        dict(kind='TEXT_WATERMARK',bbox=[.79,.03,.93,.07],confidence=.88,preserve_overlap_risk='MEDIUM',owner='UNKNOWN',overlay_role='ADDED_WATERMARK'),
        dict(kind='PRODUCT_PRINT',bbox=[.23,.8,.74,.85],confidence=.98,preserve_overlap_risk='HIGH',owner='PACKAGING')])

class HeaderFooterTests(unittest.TestCase):
    def test_explicit_model_delete_of_top_store_bottom_stock_poster_is_not_downgraded(self):
        from mye_c_automation.ai_judge.image_action_decision import apply_visual_rules
        raw=poster();before=copy.deepcopy(raw)
        adjusted,_=apply_visual_rules(raw)
        self.assertEqual(adjusted['decision'],'DELETE');self.assertEqual(raw,before)

    def test_ordinary_photo_manufacturer_banner_small_badge_and_raw_review_protected(self):
        from mye_c_automation.ai_judge.image_action_decision import is_seller_promotional_composite
        variants=[]
        p=poster();p['visual_class']='TOY_PRODUCT';variants.append(p)
        p=poster();p['watermarks'][0]['owner']='MANUFACTURER';variants.append(p)
        p=poster();p['watermarks'][0]['bbox']=[.33,0,.4,.04];variants.append(p)
        p=poster();p['watermarks'][1]['bbox']=[0,.4,.2,.48];variants.append(p)
        p=poster();p['decision']='REVIEW';variants.append(p)
        for p in variants:
            with self.subTest(p=p):self.assertFalse(is_seller_promotional_composite(p))

    def test_offline_reassessment_preserves_model_reply_and_requires_narrow_old_blocker(self):
        from mye_c_automation.ai_judge.image_action_decision import reassess_seller_poster
        raw=poster();old=dict(decision='REVIEW',observation=dict(raw,decision='REVIEW'),results=[raw],models=['deepseek-v4.1-flash'],policy_adjustments=[],reason_codes=['TEXT_OWNERSHIP_UNRESOLVED'])
        before=copy.deepcopy(old);new=reassess_seller_poster(old)
        self.assertEqual(new['decision'],'DELETE');self.assertEqual(old,before);self.assertEqual(new['results'],old['results'])
        for reasons in (['MODEL_OUTPUT_INCOMPLETE'],['RETAIL_BOX_UNRESOLVED']):
            p=copy.deepcopy(old);p['reason_codes']=reasons;self.assertEqual(reassess_seller_poster(p),p)
        p=copy.deepcopy(old);p['results'][0]['abstain']=True;self.assertEqual(reassess_seller_poster(p),p)

    def test_bound_reassessment_leaves_audit_files_unchanged_and_tamper_is_rejected(self):
        from mye_c_automation.v2_remediation import record_seller_reassessment,verify_audit
        from mye_c_automation.product_state import canonical_state_hash
        from mye_c_automation.automation_policy import AutomationPolicy
        from mye_c_automation.resources import resource_path
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);product={'id':5099};digest='a'*64;raw=poster()
            old=dict(decision='REVIEW',observation=dict(raw,decision='REVIEW'),results=[raw],models=['deepseek-v4.1-flash'],policy_adjustments=[],reason_codes=['TEXT_OWNERSHIP_UNRESOLVED'])
            files={'audit_product.json':product,'full_inventory.json':{'contents':{}},'full_ai_judgements.json':{digest:old}}
            for n,v in files.items():(root/n).write_text(json.dumps(v),encoding='utf-8')
            (root/'full_audit_evidence_manifest.json').write_text(json.dumps({'files':[dict(path=n,sha256=hashlib.sha256((root/n).read_bytes()).hexdigest()) for n in files]}))
            original={p.name:p.read_bytes() for p in root.iterdir()}
            config=json.loads(resource_path('config/automation.v2.example.json').read_text());config['delete_decorated_composites']=True
            policy=AutomationPolicy(config);job={'input_state_sha256':canonical_state_hash(product)}
            record_seller_reassessment(root,job,policy)
            _,results=verify_audit(root,job);self.assertEqual(results[digest]['decision'],'DELETE')
            self.assertEqual(original,{n:(root/n).read_bytes() for n in original})
            path=root/'v2_policy_reassessment.json';receipt=json.loads(path.read_text());receipt['overrides'][digest]['decision']='KEEP';path.write_text(json.dumps(receipt))
            with self.assertRaises(ValueError):verify_audit(root,job)
