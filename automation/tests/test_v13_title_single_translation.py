import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from types import SimpleNamespace

from mye_c_automation.visual_quality import VisualQualityInspector
import test_v13_account_cli as cli


class SingleTranslationTests(unittest.TestCase):
    def test_missing_brand_reviewer_never_reuses_title_rules(self):
        from mye_c_automation.semantic_remedies import build
        title=Mock(return_value={'ok':True,'evidence_ids':['TITLE_RULES_ONLY']})
        product={'title':'NA-H74 威震天','titleEn':'Old title','brandId':200014695,'identityJson':{'modelCode':'NA-H74'}}
        candidates,_,_=build(product,{'anomalies':[{'type':'brand_rule'}]},[],[],SimpleNamespace(validate_title=title),7)
        self.assertNotIn('BRAND_CODE',{r['action'] for r in candidates})
        title.assert_not_called()

    def test_brand_gate_keeps_independent_review(self):
        with tempfile.TemporaryDirectory() as temp:
            judge=Mock()
            judge.classify.return_value={'status':'CLEAN','results':[
                {'decision':'MATCH','confidence':.95,'abstain':False},
                {'decision':'MATCH','confidence':.96,'abstain':False}]}
            inspector=VisualQualityInspector(temp,{},judge=judge)
            self.assertTrue(inspector.validate_brand({}, {'ok':True,'titleEn':'Hot Sale NA-H74'})['ok'])
            judge.classify.assert_called_once()

    def test_title_and_translation_checks_make_no_model_calls(self):
        with tempfile.TemporaryDirectory() as temp:
            judge=Mock();judge.classify.side_effect=AssertionError('title model review disabled')
            inspector=VisualQualityInspector(temp,{},judge=judge)
            product={'titleEn':'Old title'}
            proposal={'ok':True,'titleEn':'Hot Sale NA-H74 Action Figures Collection Gifts'}
            checked=inspector.validate_title(product,proposal)
            self.assertTrue(checked['ok'])
            self.assertEqual(checked['review_status'],'NOT_REVIEWED')
            product.update(titleEn=proposal['titleEn'],titleTranslationZh='一次回译')
            self.assertTrue(inspector.validate_title(product,dict(proposal,verify_translation=True))['ok'])
            judge.classify.assert_not_called()

    def test_standard_cli_saves_once_translates_once_without_title_review(self):
        with tempfile.TemporaryDirectory() as temp:
            judge=Mock();judge.classify.side_effect=AssertionError('no title review')
            directory=Path(temp)/'title-evidence';directory.mkdir()
            inspector=VisualQualityInspector(directory,{},judge=judge)
            writer,path,_,error=cli.AccountCliTests().execute(temp,case='title',title_validator=inspector.validate_title)
            self.assertIsNone(error,repr(error))
            self.assertEqual((writer.saves,writer.uploads,writer.translations),(1,0,1))
            judge.classify.assert_not_called()
            self.assertTrue(json.loads((path/'content_validation.json').read_text(encoding='utf-8'))['ok'])
            title=next(r for r in json.loads((path/'semantic_validation.json').read_text(encoding='utf-8'))['candidates'] if r['action']=='TITLE_REWRITE')
            self.assertEqual(title['title_review_status'],'NOT_REVIEWED')
            self.assertNotIn('bidirectional_consistency',title['checks'])
            self.assertNotIn('title_semantics',{r['task_type'] for r in json.loads((path/'ai_queue.json').read_text(encoding='utf-8'))['items']})

    def test_translation_error_hangs_without_automatic_retranslation_or_resave(self):
        with tempfile.TemporaryDirectory() as temp:
            judge=Mock();judge.classify.side_effect=AssertionError('no title review')
            directory=Path(temp)/'title-evidence';directory.mkdir()
            inspector=VisualQualityInspector(directory,{},judge=judge)
            writer,path,_,error=cli.AccountCliTests().execute(temp,case='title_translate_error',title_validator=inspector.validate_title)
            self.assertIsNone(error,repr(error))
            self.assertEqual((writer.saves,writer.uploads,writer.translations),(1,0,1))
            self.assertEqual(json.loads((path/'state.json').read_text(encoding='utf-8'))['state'],'TRANSLATION_PENDING')
            judge.classify.assert_not_called()
