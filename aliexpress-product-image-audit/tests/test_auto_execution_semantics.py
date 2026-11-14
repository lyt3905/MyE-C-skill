import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from copy import deepcopy
from executor.service import ExecutorService
from test_local_execution import ApplyTests

class ExecuteSemanticsTests(unittest.TestCase):
    def test_no_actual_change_never_saves(self):
        with tempfile.TemporaryDirectory() as root:
            writer,plan=ApplyTests().fixture(root)
            writer.translate=Mock()
            plan['desired']={'titleEn':writer.data['titleEn']}
            result=ExecutorService(Mock(),writer,root).execute(plan,{},False)
            self.assertEqual(result['site_save_calls'],0);self.assertEqual(writer.calls,0)
            writer.translate.assert_not_called()
    def test_translation_failure_is_pending_without_second_save(self):
        with tempfile.TemporaryDirectory() as root:
            writer,plan=ApplyTests().fixture(root)
            plan['desired']={'titleEn':'Updated title'};plan['post_actions']={'translate_title':True}
            writer.translate=Mock(side_effect=TimeoutError('translation timeout'))
            result=ExecutorService(Mock(),writer,root).execute(plan,{},False)
            self.assertEqual(writer.calls,1);writer.translate.assert_called_once()
            self.assertEqual(result['translation_status'],'TRANSLATION_PENDING')
            self.assertEqual(result['site_save_calls'],1)
