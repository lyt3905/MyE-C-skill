import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

import product_state
import test_v13_account_cli as cli


class DescriptionHeaderTests(unittest.TestCase):
    def test_description_presence_and_value_type_are_not_normalized_away(self):
        for expected,observed in (({}, {'descriptionJson':None}),({'descriptionJson':None}, {}),
                                  ({'descriptionJson':1}, {'descriptionJson':True})):
            with self.subTest(expected=expected,observed=observed):
                self.assertFalse(product_state.saved_state_matches(expected,observed,source=expected))

    def snapshots(self):
        source={'titleEn':'Old title','descriptionJson':json.dumps([
            {'type':'text','texts':[{'class':'title','content':'Old title'}]},
            {'type':'text','texts':[{'content':'Collected body'}]},
            {'type':'image','url':'https://never-fetch/body'}])}
        expected=deepcopy(source);expected['titleEn']='New title'
        observed=deepcopy(expected);doc=json.loads(source['descriptionJson'])
        doc[0]['texts'][0]['content']='New title';observed['descriptionJson']=json.dumps(doc)
        return source,expected,observed

    def test_exact_site_header_sync_is_rejected_without_mutating_snapshots(self):
        source,expected,observed=self.snapshots();original=deepcopy((source,expected,observed))
        self.assertFalse(product_state.saved_state_matches(expected,observed,source=source))
        self.assertEqual((source,expected,observed),original)
        self.assertNotEqual(product_state.canonical_state_hash(expected),product_state.canonical_state_hash(observed))

    def test_body_image_style_wrong_header_and_unbound_source_remain_rejected(self):
        for change in ('body','image','style','wrong_title','unbound_source'):
            with self.subTest(change=change):
                source,expected,observed=self.snapshots();doc=json.loads(observed['descriptionJson'])
                if change=='body':doc[1]['texts'][0]['content']='Changed body'
                if change=='image':doc[2]['url']='https://never-fetch/changed'
                if change=='style':doc[0]['style']={'color':'red'}
                if change=='wrong_title':doc[0]['texts'][0]['content']='Unrelated title'
                if change=='unbound_source':source['titleEn']='Unrelated source title'
                observed['descriptionJson']=json.dumps(doc)
                self.assertFalse(product_state.saved_state_matches(expected,observed,source=source))

    def test_outbound_plan_still_cannot_edit_description(self):
        from final_state import validate_final_snapshot
        source,expected,observed=self.snapshots()
        source.update(images={'main':['https://x/m'],'detail':['https://x/d']},skus=[])
        observed.update(images=deepcopy(source['images']),skus=[])
        self.assertFalse(validate_final_snapshot(observed,context={'before':source})['ok'])
        self.assertFalse(validate_final_snapshot(observed,context={'before':source,'saved_readback':True})['ok'])

    def test_standard_cli_rejects_header_body_and_image_changes(self):
        for case in ('backend_header','backend_header_body','backend_header_image'):
            with self.subTest(case=case),tempfile.TemporaryDirectory() as temp:
                writer,path,_,error=cli.AccountCliTests().execute(temp,case=case)
                self.assertEqual((writer.saves,writer.uploads),(1,0))
                self.assertIsNotNone(error);self.assertEqual(writer.translations,0)
                state=json.loads((path/'state.json').read_text(encoding='utf-8'))
                self.assertEqual(state['state'],'APPLY_UNKNOWN')
