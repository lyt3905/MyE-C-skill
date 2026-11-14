import tempfile
import unittest
import test_auto_semantic_workflow as helpers

class BrandWorkflowTests(unittest.TestCase):
    def test_unambiguous_known_brand_field_is_rewritten_and_readback_verified(self):
        with tempfile.TemporaryDirectory() as root:
            result,writer,product=helpers.SemanticWorkflowTests().execute_case(root,'brand')
            self.assertEqual(result['status'],'AUTO_VERIFIED',result)
            self.assertEqual(product['brandId'],200017853)
            self.assertEqual((writer.saves,writer.translations),(1,0))
            self.assertEqual(product['titleEn'],'Old title')
