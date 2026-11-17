import copy
import unittest
from mye_c_automation.automation_policy import AutomationPolicy
from mye_c_automation.auto_decision import decide

CONFIG={'schema':'automation-policy/v1','enabled':True,'mode':'auto_apply','shop_allowlist':[7], 'pid_allowlist':[], 'max_products_per_run':10,'max_site_save_per_job':1,'max_uploads_per_job':12,'max_ai_requests_per_job':45,'allow_actions':{'REPLACE_TWIN':True,'CROP_BANNER':True},'preserve_product_status':True,'require_live_dry_run':True,'require_post_write_readback':True,'require_content_validation':True,'halt_batch_after_unknown_write':True,'stop_on_global_integrity_error':True}

def remedy():
    return {'remedy_id':'REM_1','item_id':'WM_MAIN_000','action':'REPLACE_TWIN','target':{'pool':'main','image_id':'MAIN_000','index':0},'source':{'type':'existing_pool','url':'https://x/b','sha256':'a'*64},'candidate_asset':None,'evidence_ids':['E1'], 'checks':{'product_identity_match':True,'source_clean':True,'candidate_visual_validation':True,'protected_elements_preserved':True,'source_bound':True,'model_match':True,'packaging_match':True},'reason_codes':['TWIN_VERIFIED']}

class AutomationPolicyTests(unittest.TestCase):
    def test_policy_binds_identity_and_actions(self):
        policy=AutomationPolicy(CONFIG)
        policy.authorize(1,7,['REPLACE_TWIN'])
        for pid,shop,actions in [(1,4,['REPLACE_TWIN']),(1,7,['ERASE_LOCAL']),(1,7,['UNKNOWN'])]:
            with self.assertRaises(ValueError): policy.authorize(pid,shop,actions)
    def test_disabled_and_budget_fail_closed(self):
        for field,value in [('enabled',False),('max_site_save_per_job',2),('preserve_product_status',False),('max_products_per_run',0)]:
            config=dict(CONFIG,**{field:value})
            with self.assertRaises(ValueError): AutomationPolicy(config).authorize(1,7,['REPLACE_TWIN'])
    def test_pid_allowlist_and_batch_limit(self):
        policy=AutomationPolicy(dict(CONFIG,pid_allowlist=[1]))
        with self.assertRaises(ValueError): policy.authorize(2,7,[])
        with self.assertRaises(ValueError): policy.authorize(1,7,[],product_count=11)
    def test_hash_covers_config(self):
        self.assertNotEqual(AutomationPolicy(CONFIG).sha256,AutomationPolicy(dict(CONFIG,max_uploads_per_job=11)).sha256)
    def test_mixed_safe_and_deferred(self):
        candidate=remedy();bad=copy.deepcopy(candidate);bad['remedy_id']='REM_2';bad['checks']['source_clean']=False
        result=decide([candidate,bad],AutomationPolicy(CONFIG),pid=1,shop=7)
        self.assertEqual([r['decision'] for r in result],['AUTO_SAFE','DEFERRED'])
    def test_global_integrity_blocks_all(self):
        self.assertEqual(decide([remedy()],AutomationPolicy(CONFIG),pid=1,shop=7,integrity_ok=False)[0]['decision'],'BLOCKED_FATAL')
    def test_missing_evidence_or_unknown_action_never_ready(self):
        for changes in ({'action':'REMOVE_CANDIDATE'},{'evidence_ids':[]},{'source':{}},{'checks':{}},{'action':'DELETE_REDUNDANT'}):
            row=dict(remedy(),**changes)
            self.assertEqual(decide([row],AutomationPolicy(CONFIG),pid=1,shop=7)[0]['decision'],'DEFERRED')
