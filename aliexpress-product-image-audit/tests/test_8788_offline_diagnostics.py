import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image
from audit_diagnostics_v2 import diagnose


class OfflineDiagnosticsTests(unittest.TestCase):
    def fixture(self,temp):
        job=Path(temp)/'job';job.mkdir();p=job/'source.png';Image.new('RGB',(800,800),'green').save(p)
        sha=hashlib.sha256(p.read_bytes()).hexdigest();wm='WM_'+sha[:16];identity='IDENTITY_'+sha[:16]
        occurrences=[{'id':pool.upper()+'_000','pool':pool,'index':0,'target_type':'image_slot','sha256':sha,'url':'https://fake/image'} for pool in ('main','detail','sku')]
        occurrences.append({'id':'SKU_ROW_000','target_type':'sku_reference','sku_row_index':0,'sku_name':'no retail box','sha256':sha,'url':'https://fake/image'})
        inventory={'contents':{sha:{'file':str(p),'width':800,'height':800,'ocr':[],'occurrence_ids':[v['id'] for v in occurrences]}},'occurrences':occurrences}
        queue={'pid':1,'items':[{'id':k,'task_type':t,'sha256':sha,'dimensions':[800,800],'evidence_ids':[k]} for k,t in ((wm,'watermark'),(identity,'product_identity'))]}
        root={'task_type':'watermark','item_id':wm,'classification':'third_party_store_banner','owner':'Example Store','location':'top','confidence':.97,'abstain':False,'evidence_ids':[wm]}
        identity_row={'task_type':'product_identity','item_id':identity,'decision':'MATCH','confidence':.97,'abstain':False,'image_type':'FIGURE','model':'DW-ES09T','color':'green','evidence_ids':[identity],'model_evidence_ids':[identity]}
        for name,data in [('full_inventory.json',inventory),('full_ai_queue.json',queue),('full_ai_judgements.json',{wm:{'results':[root,root]},identity:{'results':[identity_row,dict(identity_row,image_type='BOX')]}})]:
            (job/name).write_text(json.dumps(data),encoding='utf-8')
        (job/'budget.sqlite').write_bytes(b'frozen fake ledger')
        return job

    def test_report_is_offline_preserves_evidence_and_explains_missing_fields(self):
        with tempfile.TemporaryDirectory() as temp:
            job=self.fixture(temp);out=Path(temp)/'report'
            before={p.name:p.read_bytes() for p in job.iterdir()}
            with patch('ai_judge.JudgeClient._request') as request,patch('site_client._SiteTransport') as site:
                result=diagnose(job,out,'DW-ES09T')
                request.assert_not_called();site.assert_not_called()
            self.assertEqual(result['new_tokens'],0)
            self.assertEqual(result['positions'],4)
            self.assertEqual(before,{p.name:p.read_bytes() for p in job.iterdir()})
            report=json.loads((out/'8788-audit-diagnostics-v2.json').read_text(encoding='utf-8'))
            self.assertEqual(report['compliance_status'],'NON_COMPLIANT')
            self.assertTrue(all(v['confirmed_findings'] for v in report['occurrences']))
            reference=next(v for v in report['occurrences'] if v['target_type']=='sku_reference')
            self.assertEqual((reference['pool'],reference['index'],reference['sku_row_index']),('sku',0,0))
            matrix=json.loads((out/'8788-unknown-reason-matrix.json').read_text(encoding='utf-8'))
            self.assertTrue(matrix['missing_optional_inputs'])
            self.assertTrue(any('coverage_complete' in v['missing_fields'] for v in matrix['rows']))
            self.assertTrue(all(isinstance(v['model_name'],str) and 'confidence' in v['original_observation'] for v in matrix['rows']))

    def test_output_inside_original_job_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            job=self.fixture(temp)
            with self.assertRaisesRegex(ValueError,'MUST_NOT_MODIFY_JOB'):diagnose(job,job/'report','DW-ES09T')
