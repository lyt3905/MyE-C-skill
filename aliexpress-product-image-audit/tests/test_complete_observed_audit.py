"""Continuation evaluates only never-called pairs, keeping schema failures UNKNOWN."""
from pathlib import Path
import tempfile
import unittest

import complete_observed_audit as ca
import observed_audit as oa
import run_8788_real_validation as rv
from test_8788_real_validation import response


def fake_parent(directory):
    parent=oa.prepare(directory,user_statement='Fake no-cap audit',authorize_real=False)
    inputs=rv.read(parent/'inputs.json');plan=rv.read(parent/'request-plan.json')
    journal=oa.Journal(parent/'observed-requests.sqlite',parent.name,create=True,mode='FAKE')
    (parent/'observed-started.json').write_text('{"mode":"FAKE"}',encoding='utf-8')
    for index,planned in enumerate(plan[:21]):
        item=next(i for i in inputs['tasks'] if i['id']==planned['item_id'])
        raw=response(item,planned['model']);sequence=journal.dispatch(item['id'],planned['model'],item['sha256'])
        if index==20:
            journal.complete(sequence,'ERROR',raw['usage'],'SCHEMA_OR_TRANSPORT_ERROR:ValueError')
        else:
            rv.write(parent/'observed-normalized'/f'{sequence:02d}.json',dict(model=planned['model'],result=rv.parse_json_content(raw['choices'][0]['message']['content']),raw_usage=raw['usage']))
            journal.complete(sequence,'SUCCESS',raw['usage'],None)
    oa.report(parent,'FAKE_PIPELINE_STOPPED',journal.rows(),'SCHEMA_OR_TRANSPORT_ERROR:ValueError',fake=True)
    return parent


class ContinuationTests(unittest.TestCase):
    def test_missing_model_a_keeps_model_b_observations_in_model_b_slot(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent=fake_parent(Path(tmp))
            def fake(model,item,context):
                raw=response(item,model)
                if item['task_type']=='watermark':
                    row=rv.parse_json_content(raw['choices'][0]['message']['content'])
                    row.update(no_marks_detected=False,marks=[dict(mark_id='B1',classification='manufacturer_branding',
                        owner='Dr.Wu',location='bottom',bbox_xyxy=[10,10,40,40],confidence=.95,abstain=False,evidence_ids=item['evidence_ids'][:1])])
                    raw['choices'][0]['message']['content']=__import__('json').dumps(row)
                return raw
            job,result=ca.complete(parent,transport=fake,fake=True)
            sha=rv.read(parent/'inputs.json')['images'][-1]['sha256']
            region=result['watermark'][sha]['regions'][0]
            self.assertIsNone(region['model_a_observation'])
            self.assertEqual(region['model_b_observation']['mark_id'],'B1')
            self.assertEqual(region['status'],'UNKNOWN')
    def test_new_workflow_automatically_finishes_after_one_item_schema_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls=[]
            def fake(model,item,context):
                calls.append((item['id'],model));raw=response(item,model)
                if len(calls)==1:raw['choices'][0]['message']['content']='{}'
                return raw
            job,result=ca.run_new(Path(tmp),user_statement='Fake observed workflow',transport=fake,fake=True)
            self.assertEqual(len(calls),24)
            self.assertEqual(len(set(calls)),24)
            self.assertEqual(result['normalized_response_count'],23)
            self.assertEqual(result['state'],'FAKE_PIPELINE_COMPLETED_WITH_EXCEPTIONS')

    def test_item_journal_keeps_one_monotonic_counter_across_schema_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal=ca.ItemJournal(Path(tmp)/'items.sqlite','fake',create=True,mode='FAKE')
            for index in range(24):
                sequence=journal.dispatch('task'+str(index),'model','a'*64)
                journal.schema_exception(sequence,None,'SCHEMA_ERROR')
                self.assertEqual(sequence,index+1)
            with self.assertRaisesRegex(rv.Blocked,'REQUEST_LIMIT'):
                journal.dispatch('extra','model','a'*64)

    def test_only_three_never_called_pairs_execute_and_keep_missing_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent=fake_parent(Path(tmp));before=rv.tree(parent);calls=[]
            def fake(model,item,context):
                calls.append((item['id'],model));return response(item,model)
            job,result=ca.complete(parent,transport=fake,fake=True)
            self.assertEqual(len(calls),3)
            self.assertEqual(result['new_provider_requests'],0)
            self.assertEqual(result['simulated_new_requests'],3)
            self.assertEqual(result['request_count'],24)
            self.assertEqual(result['normalized_response_count'],23)
            self.assertEqual(result['state'],'FAKE_PIPELINE_COMPLETED_WITH_EXCEPTIONS')
            self.assertEqual(rv.tree(parent),before)
            self.assertFalse((job/'observed-normalized/21.json').exists())
            self.assertTrue((job/'observed-normalized/24.json').exists())

    def test_continuation_cannot_be_repeated(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent=fake_parent(Path(tmp));ca.complete(parent,transport=lambda m,i,c:response(i,m),fake=True)
            with self.assertRaisesRegex(rv.Blocked,'CONTINUATION_ALREADY_CLAIMED'):
                ca.complete(parent,transport=lambda *a:self.fail('sent'),fake=True)

    def test_completed_child_cannot_be_used_to_replay_old_pairs(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent=fake_parent(Path(tmp));child,result=ca.complete(parent,transport=lambda m,i,c:response(i,m),fake=True)
            with self.assertRaises(rv.Blocked):
                ca.complete(child,transport=lambda *a:self.fail('sent'),fake=True)

    def test_real_continuation_requires_real_authorization(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent=fake_parent(Path(tmp))
            with self.assertRaisesRegex(rv.Blocked,'REAL_AUTHORIZATION_REQUIRED'):
                ca.complete(parent,transport=lambda *a:self.fail('sent'),fake=False)

    def test_schema_failure_is_one_exception_and_remaining_pairs_still_execute(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent=fake_parent(Path(tmp));calls=[]
            def fake(model,item,context):
                calls.append(1);raw=response(item,model)
                if len(calls)==1:raw['choices'][0]['message']['content']='{}'
                return raw
            job,result=ca.complete(parent,transport=fake,fake=True)
            self.assertEqual(len(calls),3)
            self.assertEqual(result['normalized_response_count'],22)
            self.assertEqual(result['schema_exception_count'],2)

    def test_transport_timeout_stops_without_retry_or_discarding_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent=fake_parent(Path(tmp));calls=[]
            def fake(*args):calls.append(1);raise TimeoutError()
            job,result=ca.complete(parent,transport=fake,fake=True)
            self.assertEqual(len(calls),1)
            self.assertIn('STOPPED',result['state'])
            self.assertEqual(result['normalized_response_count'],20)

    def test_plan_tamper_cannot_trigger_other_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent=fake_parent(Path(tmp));plan=rv.read(parent/'request-plan.json')
            plan[-1]['sha256']='0'*64;rv.write(parent/'request-plan.json',plan)
            with self.assertRaises(rv.Blocked):
                ca.complete(parent,transport=lambda *a:self.fail('sent'),fake=True)


if __name__=='__main__':unittest.main()
