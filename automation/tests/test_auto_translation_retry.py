import tempfile
import unittest
from copy import deepcopy
from unittest.mock import Mock
from mye_c_automation.executor.local import LocalExecutor
from mye_c_automation.automation_policy import AutomationPolicy
from test_auto_decision import CONFIG
import test_local_execution as helpers

class TranslationRetryTests(unittest.TestCase):
    def test_retry_is_translation_only_and_durably_limited(self):
        with tempfile.TemporaryDirectory() as root:
            helper=helpers.ApplyTests();writer,plan=helper.fixture(root)
            policy=AutomationPolicy(dict(CONFIG,allow_actions={'TITLE_REWRITE':True}))
            plan.update(schema='token-opt-plan/v3',automation={'policy_sha256':policy.sha256,'actions':['TITLE_REWRITE']})
            plan['post_actions']={'translate_title':True}
            writer.translate=Mock(side_effect=TimeoutError('response lost'))
            executor=LocalExecutor(writer,root)
            receipt=executor.execute_auto(plan,policy)
            self.assertEqual(receipt['translation_status'],'TRANSLATION_PENDING')
            self.assertEqual(writer.calls,1)
            def translate(pid,title):writer.data['titleTranslationZh']='新标题'
            writer.translate=Mock(side_effect=translate)
            result=executor.retry_translation(plan,policy)
            self.assertEqual(result['translation_status'],'TRANSLATED')
            self.assertEqual(writer.calls,1);writer.translate.assert_called_once()
            with self.assertRaises((ValueError,FileExistsError)):executor.retry_translation(plan,policy)
            self.assertEqual(writer.calls,1)
    def test_changed_saved_fields_prevent_translation_retry(self):
        with tempfile.TemporaryDirectory() as root:
            helper=helpers.ApplyTests();writer,plan=helper.fixture(root)
            policy=AutomationPolicy(dict(CONFIG,allow_actions={'TITLE_REWRITE':True}))
            plan.update(schema='token-opt-plan/v3',automation={'policy_sha256':policy.sha256,'actions':['TITLE_REWRITE']})
            plan['post_actions']={'translate_title':True};writer.translate=Mock(side_effect=TimeoutError())
            executor=LocalExecutor(writer,root);executor.execute_auto(plan,policy)
            writer.data['titleEn']='user edit';writer.translate.reset_mock()
            with self.assertRaisesRegex(ValueError,'STATE_DRIFT'):executor.retry_translation(plan,policy)
            writer.translate.assert_not_called();self.assertEqual(writer.calls,1)
