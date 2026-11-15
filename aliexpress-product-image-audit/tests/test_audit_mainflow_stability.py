from current_source_fixtures import freeze_current_source
"""Main-flow resilience uses Fake transport and preserves strict audit verdicts."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import observed_audit as oa
import complete_observed_audit as ca
import run_8788_real_validation as rv
from test_8788_real_validation import response


class MainFlowTests(unittest.TestCase):
    def setUp(self):freeze_current_source(self)

    def test_schema_errors_complete_in_one_job_without_parent_or_retries(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls=[]
            def fake(model,item,context):
                calls.append((item['id'],model));raw=response(item,model)
                if len(calls) in (1,24):raw['choices'][0]['message']['content']='{}'
                return raw
            with patch.object(ca,'complete',side_effect=AssertionError('No child Job needed')):
                job,result=ca.run_new(Path(tmp),user_statement='Fake mainflow',transport=fake,fake=True)
            self.assertEqual(len(set(calls)),24)
            self.assertEqual(result['request_count'],24)
            self.assertEqual(result['normalized_response_count'],22)
            self.assertEqual(result['schema_exception_count'],2)
            self.assertEqual(result['state'],'FAKE_PIPELINE_COMPLETED_WITH_EXCEPTIONS')
            self.assertEqual(len(list(Path(tmp).glob('OBSERVED_*'))),1)

    def test_empty_length_response_is_an_item_exception_and_other_tasks_continue(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls=[]
            def fake(model,item,context):
                calls.append(1);raw=response(item,model)
                if len(calls)==1:
                    raw['choices'][0]['message']['content']='';raw['choices'][0]['finish_reason']='length'
                return raw
            job,result=ca.run_new(Path(tmp),user_statement='Fake mainflow',transport=fake,fake=True)
            self.assertEqual(len(calls),24)
            self.assertEqual(result['normalized_response_count'],23)
            self.assertEqual(result['state'],'FAKE_PIPELINE_COMPLETED_WITH_EXCEPTIONS')

    def test_progress_is_durable_before_sender_and_unknown_does_not_block_next(self):
        with tempfile.TemporaryDirectory() as tmp:
            job=oa.prepare(Path(tmp),user_statement='Fake',authorize_real=False)
            seen=[]
            def fake(model,item,context):
                status=oa.read_status(job)
                seen.append(status['request_count'])
                self.assertEqual(status['execution_status'],'RUNNING')
                raw=response(item,model);row=json.loads(raw['choices'][0]['message']['content'])
                row['confidence']=.5;row['abstain']=True
                raw['choices'][0]['message']['content']=json.dumps(row);return raw
            result=oa.run(job,transport=fake,fake=True,continue_item_errors=True)
            self.assertEqual(seen,list(range(1,25)))
            self.assertFalse(result['all_image_checks_conclusive'])
            status=oa.read_status(job)
            self.assertEqual(status['execution_status'],'COMPLETED')
            self.assertFalse(status['all_image_checks_conclusive'])

    def test_timeout_stops_without_retry_and_exposes_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls=[]
            def fake(*args):calls.append(1);raise TimeoutError()
            job,result=ca.run_new(Path(tmp),user_statement='Fake',transport=fake,fake=True)
            self.assertEqual(len(calls),1)
            self.assertEqual(result['state'],'FAKE_PIPELINE_STOPPED')
            status=oa.read_status(job)
            self.assertEqual(status['execution_status'],'STOPPED')
            self.assertEqual(status['stop_reason'],'TIMEOUT')

    def test_model_mismatch_remains_fatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls=[]
            def fake(model,item,context):
                calls.append(1);raw=response(item,model);raw['model']='other';return raw
            job,result=ca.run_new(Path(tmp),user_statement='Fake',transport=fake,fake=True)
            self.assertEqual(len(calls),1)
            self.assertEqual(result['stop_reason'],'ACTUAL_MODEL_ID_CHANGED')


class MainEntryTests(unittest.TestCase):
    def test_main_entry_defaults_to_offline_and_does_not_create_site_job(self):
        with patch.object(oa,'prepare',return_value=Path('fake-job')) as prepare, \
                patch.object(ca,'run_new',side_effect=AssertionError('No execution in default mode')), \
                contextlib.redirect_stdout(io.StringIO()):
            ca.main(['--output-dir','fake-output'])
        self.assertFalse(prepare.call_args.kwargs['authorize_real'])

    def test_status_command_only_reads_local_progress(self):
        with tempfile.TemporaryDirectory() as tmp:
            job=Path(tmp)
            rv.write(job/'observed-progress.json',dict(execution_status='COMPLETED_WITH_EXCEPTIONS',request_count=24))
            with patch.object(oa,'prepare',side_effect=AssertionError('No new Job for status')), \
                    patch('urllib.request.urlopen',side_effect=AssertionError('Network')),contextlib.redirect_stdout(io.StringIO()) as output:
                ca.main(['--status-job',str(job)])
            self.assertEqual(json.loads(output.getvalue())['request_count'],24)

    def test_old_report_status_can_be_read_without_updating_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            job=Path(tmp)
            rv.write(job/'observed-audit-report.json',dict(state='PIPELINE_COMPLETED_WITH_EXCEPTIONS',request_count=24,
                normalized_response_count=23,all_image_checks_conclusive=False,stop_reason=None))
            before=rv.tree(job);status=oa.read_status(job)
            self.assertEqual(status['execution_status'],'COMPLETED_WITH_EXCEPTIONS')
            self.assertEqual(rv.tree(job),before)


if __name__=='__main__':unittest.main()
