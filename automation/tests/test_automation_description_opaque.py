import unittest
from unittest.mock import patch
from mye_c_automation import product_state

class OpaqueDescriptionTests(unittest.TestCase):
    def test_description_header_is_opaque_and_any_change_is_rejected(self):
        before='[{"type":"text","texts":[{"class":"title","content":"Old"}]}]'
        after=before.replace('Old','New')
        with patch('mye_c_automation.product_state.json.loads',side_effect=AssertionError('Description must not be parsed')):
            self.assertFalse(product_state.description_content_preserved(before,after,source_title='Old',saved_title='New'))
            self.assertFalse(product_state.saved_state_matches({'descriptionJson':before},{'descriptionJson':after},source={'titleEn':'Old'}))
            self.assertTrue(product_state.description_content_preserved(before,before))
    def test_description_type_and_presence_remain_exact(self):
        for old,new in (({}, {'descriptionJson':None}),({'descriptionJson':1},{'descriptionJson':True}),({'descriptionJson':{}},{'descriptionJson':'{}'})):
            with self.subTest(old=old,new=new):self.assertFalse(product_state.saved_state_matches(old,new,source=old))
