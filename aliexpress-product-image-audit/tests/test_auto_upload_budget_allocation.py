import unittest,copy
from automation_policy import AutomationPolicy
from auto_decision import decide
from test_auto_decision import CONFIG,remedy

class UploadBudgetAllocationTests(unittest.TestCase):
    def candidate(self,index,digest):
        row=remedy();row.update(remedy_id='REM_'+str(index),item_id='WM_MAIN_'+str(index).zfill(3),action='CROP_BANNER')
        row['target']={'pool':'main','index':index,'image_id':'MAIN_'+str(index).zfill(3)}
        row['source']={'type':'generated_crop','sha256':digest}
        row['candidate_asset']={'path':str(index)+'.png','sha256':digest,'pool':'main','index':index}
        row['checks'].update(subject_bounds_safe=True,ocr_pass=True,residual_pass=True,template_pass=True)
        return row
    def test_zero_upload_budget_defers_asset_without_global_failure(self):
        policy=AutomationPolicy(dict(CONFIG,max_uploads_per_job=0))
        self.assertEqual(decide([self.candidate(0,'a'*64)],policy,pid=1,shop=7)[0]['decision'],'DEFERRED')
    def test_distinct_assets_use_stable_budget_and_identical_assets_share_it(self):
        policy=AutomationPolicy(dict(CONFIG,max_uploads_per_job=1))
        distinct=decide([self.candidate(0,'a'*64),self.candidate(1,'b'*64)],policy,pid=1,shop=7)
        self.assertEqual([r['decision'] for r in distinct],['AUTO_SAFE','DEFERRED'])
        same=decide([self.candidate(0,'a'*64),self.candidate(1,'a'*64)],policy,pid=1,shop=7)
        self.assertEqual([r['decision'] for r in same],['AUTO_SAFE','AUTO_SAFE'])
