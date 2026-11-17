import copy
import json
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from mye_c_automation.product_state import saved_state_matches, description_content_preserved


class GeneratedTitleReadbackTests(unittest.TestCase):
    def states(self):
        nodes = [dict(type='text', shopTitle=True, generatedBy='INGEST_POST_PROCESS',
                      generatedRole='SHOP_TITLE', texts=[dict(class_='title', content='Old')]),
                 dict(type='text', content='Protected body')]
        nodes[0]['texts'][0]['class'] = nodes[0]['texts'][0].pop('class_')
        before = dict(titleEn='Old', descriptionJson=json.dumps(nodes))
        expected = dict(before, titleEn='New')
        nodes[0]['texts'][0]['content'] = 'New'
        observed = dict(expected, descriptionJson=json.dumps(nodes))
        return before, expected, observed

    def test_saved_title_accepts_only_exact_system_generated_header_mirror(self):
        before, expected, observed = self.states()
        self.assertTrue(saved_state_matches(expected, observed, source=before))
        self.assertFalse(description_content_preserved(expected['descriptionJson'], observed['descriptionJson'], source_title='Old', saved_title='New'))
        self.assertFalse(saved_state_matches(expected, observed))

    def test_body_change_or_missing_marker_stays_blocked(self):
        before, expected, observed = self.states()
        for mutate in (lambda x: x[1].update(content='Changed'),
                       lambda x: x[0].pop('generatedRole'),
                       lambda x: x[0]['texts'][0].update(content='Wrong')):
            nodes=json.loads(observed['descriptionJson']);mutate(nodes)
            changed=dict(observed,descriptionJson=json.dumps(nodes))
            self.assertFalse(saved_state_matches(expected,changed,source=before))

    def test_identical_title_or_wrong_source_cannot_authorize_header_change(self):
        before, expected, observed = self.states()
        self.assertFalse(saved_state_matches(expected, observed, source=expected))
        self.assertFalse(saved_state_matches(expected, observed, source=dict(before,titleEn='Other')))

    def test_unmarked_original_header_is_not_eligible(self):
        before, expected, observed = self.states()
        nodes=json.loads(expected['descriptionJson']);nodes[0].pop('shopTitle')
        expected['descriptionJson']=json.dumps(nodes)
        self.assertFalse(saved_state_matches(expected,observed,source=before))

    def test_public_workflow_accepts_backend_mirror_and_recovers_without_repeat_save(self):
        from test_title_workflow_v2 import TitleWorkflowTests
        for lost in (False,True):
            with self.subTest(lost_response=lost), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);h,f=TitleWorkflowTests().fixture(root)
                before,_,_=self.states()
                f['writer'].state['titleEn']='Old'
                f['writer'].state['descriptionJson']=before['descriptionJson']
                f['original']=copy.deepcopy(f['writer'].state)
                save=f['writer'].save
                def mirrored(*args,**kwargs):
                    save(*args,**kwargs)
                    nodes=json.loads(f['writer'].state['descriptionJson'])
                    nodes[0]['texts'][0]['content']=f['writer'].state['titleEn']
                    f['writer'].state['descriptionJson']=json.dumps(nodes)
                    if lost:raise TimeoutError('lost response')
                with patch.object(f['writer'],'save',side_effect=mirrored):
                    _,result,text=h.invoke(root,f)
                if lost:
                    calls=dict(f['counters'])
                    _,result,text=h.invoke(root,f,'--resume',result['job_id'])
                    for key in ('saves','uploads','model_calls'):
                        self.assertEqual(f['counters'][key],calls[key])
                self.assertEqual(result['status'],'AUTO_VERIFIED',text)
                self.assertEqual(f['counters']['saves'],1)
