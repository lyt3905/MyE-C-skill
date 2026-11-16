"""The image save protocol must not reset the existing presale switch."""
import copy
import json
import tempfile
import unittest
from unittest.mock import patch
from mye_c_automation.site_client import _SiteTransport
from mye_c_automation.executor.site_write_client import SiteWriteClient
from mye_c_automation.product_state import canonical_state_hash
import test_v2_workflow as workflow


class PresalePreservationTests(unittest.TestCase):
    def transport(self,value=True,present=True):
        product=dict(id=4086,titleEn='Original',descriptionJson={'opaque':[1]},images=dict(main=['https://fake/1'],detail=['https://fake/2'],sku=['https://fake/1']),skus=[],price=12,weight=.3,identityJson={})
        if present:product['presale']=value
        sent=[]
        site=_SiteTransport.__new__(_SiteTransport)
        site.product=lambda pid:copy.deepcopy(product)
        def call(path,data=None,method=None):
            sent.append(copy.deepcopy(data))
            saved=copy.deepcopy(product);saved.update(data);saved['presale']=data.get('presale',False)
            return dict(data=saved)
        site.call=call
        return site,product,sent

    def test_transport_preserves_true_false_and_original_type(self):
        for value in (True,False,None):
            with self.subTest(value=value):
                site,product,sent=self.transport(value)
                reply=site.save(4086,images=product['images'],expected_state_hash=canonical_state_hash(product))
                self.assertEqual(reply['data']['presale'],value)
                self.assertIs(type(sent[0]['presale']),type(value))
                self.assertEqual(sent[0]['descriptionJson'],product['descriptionJson'])

    def test_privileged_adapter_passes_presale_without_casting(self):
        site,product,sent=self.transport(True)
        writer=SiteWriteClient(site)
        result=writer.save(4086,product,expected_state_sha256=canonical_state_hash(product))
        self.assertIs(result['data']['presale'],True)
        self.assertIs(sent[0]['presale'],True)
        self.assertEqual(writer.metrics['site_save_calls'],1)

    def test_absent_presale_is_not_invented(self):
        site,product,sent=self.transport(present=False)
        site.save(4086,expected_state_hash=canonical_state_hash(product))
        self.assertNotIn('presale',sent[0])

    def test_only_updated_timestamp_is_separate_from_protected_business_fields(self):
        from mye_c_automation.v2_remediation import protected_snapshot
        before=dict(presale=True,updatedAt='old',descriptionJson={'opaque':1},images={},skus=[dict(price=12,skuImageUrl='https://fake/1')])
        changed=copy.deepcopy(before);changed['updatedAt']='new'
        self.assertEqual(protected_snapshot(before),protected_snapshot(changed))
        for change in (dict(presale=False),dict(descriptionJson='changed'),dict(other_business_flag=False)):
            after=copy.deepcopy(changed);after.update(change)
            self.assertNotEqual(protected_snapshot(before),protected_snapshot(after))
        self.assertEqual(before['updatedAt'],'old')

    def test_v2_readback_reports_timestamp_but_rejects_presale_drift(self):
        from mye_c_automation.v2_remediation import verify_content
        with tempfile.TemporaryDirectory() as root:
            s=workflow.V2WorkflowTests.scenario(self,root,['KEEP','KEEP'],two_sku_rows=True)
            plan=json.loads((s['root']/'plan.v2.json').read_text())
            after=copy.deepcopy(s['product']);after['updatedAt']='new'
            with patch.object(s['writer'],'product',return_value=after):result=verify_content(s['root'],plan,s['writer'])
            self.assertTrue(result['ok'])
            self.assertTrue(result['protected_fields_exact'])
            self.assertEqual(result['server_metadata_changes'][0]['field'],'updatedAt')
            after['presale']=False
            with patch.object(s['writer'],'product',return_value=after):result=verify_content(s['root'],plan,s['writer'])
            self.assertFalse(result['ok'])
            self.assertFalse(result['protected_fields_exact'])


if __name__=='__main__':unittest.main()
