import json
import unittest
from unittest.mock import Mock
from site_client import _SiteTransport
from product_state import canonical_state_hash

class WireIdentityTests(unittest.TestCase):
    def test_save_serializes_identity_without_losing_logo_and_weight(self):
        site=object.__new__(_SiteTransport)
        product={'id':1,'weight':0.2,'identityJson':{'logoCode':'keep','modelCode':'NA-H74'},'images':{'main':['https://x/a']},'skus':[]}
        site.product=Mock(return_value=product);site.call=Mock(return_value={'success':True})
        site.save(1,extra={'titleEn':'New'},expected_state_hash=canonical_state_hash(product))
        args=site.call.call_args
        self.assertEqual(args.args[0],'/api/admin/products/1?autoSave=true')
        self.assertIsInstance(args.args[1]['identityJson'],str)
        self.assertEqual(json.loads(args.args[1]['identityJson']),product['identityJson'])
        self.assertEqual(args.args[1]['weight'],0.2)
    def test_identity_representation_does_not_create_false_state_drift(self):
        self.assertEqual(canonical_state_hash({'identityJson':{'logoCode':'keep','modelCode':'NA-H74'}}),canonical_state_hash({'identityJson':'{"modelCode":"NA-H74", "logoCode":"keep"}'}))
