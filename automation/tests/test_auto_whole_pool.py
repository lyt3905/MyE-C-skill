import unittest
from mye_c_automation.audit_one import _image_urls

class WholePoolTests(unittest.TestCase):
    def test_description_and_auxiliary_pools_are_ignored(self):
        product={'images':{'main':['https://x/main'],'detail':['https://x/detail'],'sku':[],'ai':['https://x/ai'],'scene':['https://x/scene']},'descriptionJson':{'blocks':[{'type':'image','url':'https://x/desc'},{'type':'text-image','imageUrl':'https://x/text-image'},{'type':'text','text':'https://x/not-image'}]},'skus':[{'skuId':1,'skuImageUrl':'https://x/sku-old'}]}
        rows=_image_urls(product)
        urls={r['url'] for r in rows}
        self.assertEqual(urls,{'https://x/main','https://x/detail','https://x/sku-old'})
        self.assertNotIn('https://x/not-image',urls)
        self.assertFalse(any(r.get('source')=='descriptionJson' for r in rows))
    def test_string_description_and_duplicate_references(self):
        product={'images':{'main':['https://x/a']},'descriptionJson':'{"blocks":[{"type":"image","url":"https://x/b"},{"type":"image","url":"https://x/b"}]}'}
        rows=_image_urls(product)
        self.assertEqual(sum(r['url']=='https://x/b' for r in rows),0)
