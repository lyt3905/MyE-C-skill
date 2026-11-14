import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from job_manager import atomic_json
from manual_review import evidence_hash
from plan_compiler import compile_plan
from approved_deletions import remove_description_images
import test_v21_compiler


class BatchDeletionTests(unittest.TestCase):
    def case(self, root):
        manager, job, directory = test_v21_compiler.CompilerReviewTests().fixture(root)
        images = {'main': ['https://test/m0', 'https://test/m1'], 'detail': ['https://test/d0', 'https://test/d1', 'https://test/d2'], 'sku': []}
        doc = [{'type': 'text', 'text': 'keep'}, {'type': 'image', 'url': images['detail'][0]}, {'type': 'image', 'url': images['detail'][1]}, {'type': 'image', 'url': images['detail'][2]}, {'type': 'image', 'url': 'https://test/footer', 'shopFooter': True}]
        atomic_json(directory/'audit_product.json', {'images': images, 'descriptionJson': json.dumps(doc)})
        targets = [{'item_id': 'A', 'pool': 'main', 'index': 0}, {'item_id': 'B', 'pool': 'detail', 'index': 0}, {'item_id': 'C', 'pool': 'detail', 'index': 1}]
        queue, raw, items = [], [], []
        for target in targets:
            key, pool, index = target['item_id'], target['pool'], target['index']
            file = directory/(key+'.bin'); file.write_bytes(key.encode())
            queue.append({'id': key, 'local': str(file), 'sha256': hashlib.sha256(file.read_bytes()).hexdigest(), 'evidence_ids': [key]})
            raw.append({'file': str(file), 'url': images[pool][index], 'kind': pool, 'index': index})
            items.append({'item_id': key, 'decision': 'REMOVE_CANDIDATE_CONFIRMED', 'authorized_actions': ['DELETE'], 'reviewer': 'test', 'reviewed_at': 'now', 'reason': 'approved', 'evidence_ids': [key]})
        atomic_json(directory/'ai_queue.json', {'items': queue})
        atomic_json(directory/'audit_raw.json', {'images': raw})
        proposed = copy.deepcopy(images); proposed['main'].pop(0); proposed['detail'] = proposed['detail'][2:]
        urls = images['detail'][:2]
        for item in items[1:]: item['original_urls'] = urls
        changes = [{'field': 'images', 'action': 'DELETE_BATCH', 'targets': targets, 'item_ids': ['A','B','C'], 'value': proposed}]
        review = {'schema': 'manual-review/v1', 'job_id': job['job_id'], 'pid': 1, 'shop_id': 7, 'evidence_sha256': evidence_hash(directory), 'items': items, 'changes': changes}
        return job, directory, review

    def test_compiles_three_deletions_and_exact_description(self):
        with tempfile.TemporaryDirectory() as root:
            job, path, review = self.case(root)
            self.assertTrue(compile_plan(path, job, review)['ok'])
            plan = json.loads((path/'plan.v2.json').read_text())
            self.assertEqual(plan['desired']['images']['detail'], ['https://test/d2'])
            self.assertNotIn('descriptionJson',plan['desired'])
            from final_state import simulate_final_snapshot
            before=json.loads((path/'audit_product.json').read_text())
            self.assertEqual(simulate_final_snapshot(before,plan)['descriptionJson'],before['descriptionJson'])

    def test_keep_and_extra_image_are_rejected(self):
        for variant in ('keep', 'extra', 'wrong_index', 'duplicate'):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as root:
                job, path, review = self.case(root)
                if variant == 'keep': review['items'][1]['decision'] = 'KEEP'
                if variant == 'extra': review['changes'][0]['value']['main'] = []
                if variant == 'wrong_index': review['changes'][0]['targets'][1]['index'] = 2
                if variant == 'duplicate': review['changes'][0]['targets'][1] = review['changes'][0]['targets'][0]
                with self.assertRaises(ValueError): compile_plan(path, job, review)

    def test_footer_text_and_unapproved_url_cannot_be_deleted(self):
        with tempfile.TemporaryDirectory() as root:
            job, path, review = self.case(root)
            review['changes'].append({'field':'descriptionJson','action':'DELETE_DESCRIPTION_URLS','item_ids':['B','C'],'value':[]})
            with self.assertRaisesRegex(ValueError, 'forbidden'): compile_plan(path, job, review)
        for block in ({'type': 'image', 'url': 'https://test/a', 'shopFooter': True}, {'type': 'image', 'url': 'https://test/a', 'text': 'keep'}):
            with self.assertRaises(ValueError): remove_description_images([block], {'https://test/a'})

    def test_changed_original_source_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            job, path, review = self.case(root)
            (path/'A.bin').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'image changed'): compile_plan(path, job, review)

    def test_preserving_existing_sku_references_does_not_allow_new_urls(self):
        with tempfile.TemporaryDirectory() as root:
            job, path, review = self.case(root)
            product = json.loads((path/'audit_product.json').read_text())
            product['skus'] = [{'skuImageUrl': 'https://test/existing-sku', 'skuName': 'with box'}]
            atomic_json(path/'audit_product.json', product)
            review['evidence_sha256'] = evidence_hash(path)
            change = review['changes'][0]
            change['preserve_existing_sku_refs'] = True
            change['value']['sku'] = ['https://test/existing-sku']
            self.assertTrue(compile_plan(path, job, review)['ok'])
            change['value']['sku'].append('https://test/unapproved')
            with self.assertRaises(ValueError): compile_plan(path, job, review)
