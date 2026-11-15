"""Authorized image-node deletion must preserve body copy and footer content."""
import copy
import json
import unittest
from product_state import canonical_state_hash
from site_client import _SiteTransport
from executor.site_write_client import SiteWriteClient


class DescriptionImageEditTests(unittest.TestCase):
    def fixture(self):
        nodes=[{'type':'text','texts':[{'content':'Original text'}]},
               {'type':'image','url':'https://fake/delete'},
               {'type':'image','url':'https://fake/keep'},
               {'type':'text','shopFooter':True,'texts':[{'content':'Footer'}]},
               {'type':'image','url':'https://fake/delete'}]
        product=dict(id=4086,descriptionJson=json.dumps(nodes),presale=True,
                     images={'detail':['https://fake/keep']},skus=[],weight=.3)
        sent=[]
        site=_SiteTransport.__new__(_SiteTransport)
        site.product=lambda pid:copy.deepcopy(product)
        site.call=lambda path,data=None,method=None:sent.append(copy.deepcopy(data)) or {'data':data}
        return nodes,product,site,sent

    def test_delete_only_exact_body_image_and_preserve_footer(self):
        from description_images import delete_body_images
        nodes,p,_,_=self.fixture()
        result=delete_body_images(p['descriptionJson'],['https://fake/delete'])
        self.assertEqual(json.loads(result),nodes[:1]+nodes[2:])
        self.assertIsInstance(result,str)

    def test_no_matching_body_image_keeps_original_bytes(self):
        from description_images import delete_body_images
        _,p,_,_=self.fixture()
        self.assertEqual(delete_body_images(p['descriptionJson'],['https://fake/absent']),p['descriptionJson'])

    def test_unmarked_tail_after_last_product_image_is_protected(self):
        from description_images import delete_body_images
        nodes=[{'type':'image','url':'https://fake/product'},
               {'type':'text-image','images':[{'url':'https://fake/tail'}]}]
        original=json.dumps(nodes)
        self.assertEqual(delete_body_images(original,['https://fake/tail']),original)

    def test_non_image_nodes_with_url_are_not_deleted(self):
        from description_images import delete_body_images
        nodes=[{'type':'text','url':'https://fake/delete','texts':[{'content':'Keep'}]}]
        self.assertEqual(delete_body_images(nodes,['https://fake/delete']),nodes)

    def test_transport_allows_only_declared_image_deletion(self):
        nodes,p,site,sent=self.fixture()
        target=json.dumps(nodes[:1]+nodes[2:])
        site.save(4086,desc=target,description_image_deletions=['https://fake/delete'],expected_state_hash=canonical_state_hash(p))
        self.assertEqual(json.loads(sent[0]['descriptionJson']),nodes[:1]+nodes[2:])
        self.assertIs(sent[0]['presale'],True)

    def test_text_mutation_and_footer_deletion_are_rejected_before_put(self):
        for mode in ('text','footer'):
            nodes,p,site,sent=self.fixture()
            target=nodes[:1]+nodes[2:]
            if mode=='text':target[0]['texts'][0]['content']='Changed'
            else:target.pop()
            with self.assertRaisesRegex(ValueError,'DESCRIPTION_MUTATION_FORBIDDEN'):
                site.save(4086,desc=json.dumps(target),description_image_deletions=['https://fake/delete'],expected_state_hash=canonical_state_hash(p))
            self.assertEqual(sent,[])

    def test_legacy_description_mutation_remains_forbidden(self):
        _,_,site,sent=self.fixture()
        with self.assertRaisesRegex(ValueError,'DESCRIPTION_MUTATION_FORBIDDEN'):
            site.save(4086,desc='[]')
        self.assertEqual(sent,[])

    def test_adapter_passes_explicit_deletion_scope(self):
        from description_images import delete_body_images
        _,p,site,sent=self.fixture();desired=copy.deepcopy(p)
        desired['descriptionJson']=delete_body_images(p['descriptionJson'],['https://fake/delete'])
        SiteWriteClient(site).save(4086,desired,expected_state_sha256=canonical_state_hash(p),description_image_deletions=['https://fake/delete'])
        self.assertEqual(sent[0]['descriptionJson'],desired['descriptionJson'])

    def test_fake_save_and_independent_readback_preserve_non_image_content(self):
        from description_images import delete_body_images
        nodes,p,site,sent=self.fixture();stored=copy.deepcopy(p)
        site.product=lambda pid:copy.deepcopy(stored)
        def save(path,data=None,method=None):
            stored.update(copy.deepcopy(data));return {'data':copy.deepcopy(stored)}
        site.call=save
        desired=copy.deepcopy(p)
        desired['descriptionJson']=delete_body_images(p['descriptionJson'],['https://fake/delete'])
        SiteWriteClient(site).save(4086,desired,expected_state_sha256=canonical_state_hash(p),description_image_deletions=['https://fake/delete'])
        independent=_SiteTransport.__new__(_SiteTransport)
        independent.product=lambda pid:copy.deepcopy(stored)
        after=SiteWriteClient(independent).product(4086)
        self.assertEqual(after,desired)
        self.assertEqual(json.loads(after['descriptionJson'])[-2:],nodes[-2:])

    def test_stale_state_rejected_without_write(self):
        _,_,site,sent=self.fixture()
        with self.assertRaisesRegex(RuntimeError,'precondition failed'):
            site.save(4086,desc='[]',description_image_deletions=['https://fake/delete'],expected_state_hash='stale')
        self.assertEqual(sent,[])

    def test_replace_body_image_preserves_properties_text_and_footer(self):
        from description_images import edit_body_images
        nodes,p,site,sent=self.fixture();nodes[1]['style']={'width':800}
        original=json.dumps(nodes)
        result=edit_body_images(original,[],{'https://fake/delete':'https://fake/repaired'})
        expected=copy.deepcopy(nodes);expected[1]['url']='https://fake/repaired'
        self.assertEqual(json.loads(result),expected)
        site.product=lambda pid:dict(p,descriptionJson=original)
        site.save(4086,desc=result,description_image_replacements={'https://fake/delete':'https://fake/repaired'},expected_state_hash=canonical_state_hash(site.product(4086)))
        self.assertEqual(sent[0]['descriptionJson'],result)

    def test_combined_deletion_replacement_adapter_path(self):
        from description_images import edit_body_images
        nodes,p,site,sent=self.fixture();desired=copy.deepcopy(p)
        mapping={'https://fake/keep':'https://fake/repaired'}
        desired['descriptionJson']=edit_body_images(p['descriptionJson'],['https://fake/delete'],mapping)
        SiteWriteClient(site).save(4086,desired,expected_state_sha256=canonical_state_hash(p),description_image_deletions=['https://fake/delete'],description_image_replacements=mapping)
        self.assertEqual(json.loads(sent[0]['descriptionJson']),[nodes[0],dict(nodes[2],url='https://fake/repaired'),*nodes[3:]])


if __name__=='__main__':unittest.main()
