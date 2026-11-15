import hashlib
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from auto_deletions import plan_deletion
from remedy_schema import validate_candidate


class DecoratedCompositeTests(unittest.TestCase):
    def test_runtime_report_metrics_do_not_invalidate_frozen_audit_evidence(self):
        import json
        import test_full_audit_remediation_bridge as bridge
        from full_product_audit import run_full_audit, remediation_inputs
        from job_manager import JobManager, atomic_json
        with tempfile.TemporaryDirectory() as directory:
            product, raw, reader, original_auditor, judge, template = bridge.FullAuditRemediationBridgeTests().fixture(directory)
            def auditor(pid, shop, output_dir, site):
                original_auditor(pid, shop, output_dir, site)
                atomic_json(output_dir/'run_metrics.json', {'machine_audit_ms': 1})
            result = run_full_audit(Path(directory)/'jobs', 1, 7, reader, judge=judge,
                                    auditor=auditor, template_config=template,image_workflow='legacy')
            manager = JobManager(Path(directory)/'jobs')
            job = manager.load(result['job_id']); root = manager.directory(job['job_id'])
            atomic_json(root/'run_metrics.json', {'machine_audit_ms': 1, 'remedy_plan_ms': 2})
            remediation_inputs(root, job)
            snapshot = root/'full_audit_run_metrics.json'
            self.assertEqual(json.loads(snapshot.read_text()), {'machine_audit_ms': 1})
            atomic_json(snapshot, {'machine_audit_ms': 999})
            with self.assertRaisesRegex(ValueError, 'FULL_AUDIT_EVIDENCE_CHANGED'):
                remediation_inputs(root, job)

    def test_report_counts_shared_images_once_and_separates_title(self):
        import json
        from automatic_report import summarize_deferred
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'full_audit_report.json').write_text(json.dumps({'occurrences': [
                {'id': 'MAIN_000', 'pool': 'main', 'index': 0, 'sha256': 'a'*64},
                {'id': 'DETAIL_000', 'pool': 'detail', 'index': 0, 'sha256': 'a'*64}]}))
            rows = [{'item_id': 'FULL_'+name, 'target': {'image_id': name}, 'reason_codes': ['OWNER_UNPROVEN']}
                    for name in ('MAIN_000', 'DETAIL_000')]
            rows.append({'item_id': 'ANOMALY_0', 'target': {}, 'reason_codes': ["{'type': 'title_prefix'}"]})
            summary = summarize_deferred(directory, rows)
            self.assertEqual(summary['record_count'], 3)
            self.assertEqual(summary['unique_image_contents'], 1)
            self.assertEqual(len(summary['image_issue_groups']), 1)
            self.assertEqual(summary['outside_image_scope_records'], ['ANOMALY_0'])

    def fixture(self, directory):
        target = Path(directory) / 'poster.png'
        retained = Path(directory) / 'box.png'
        Image.new('RGB', (800, 800), 'red').save(target)
        Image.new('RGB', (800, 800), 'green').save(retained)
        digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
        product = {'images': {'main': ['https://x/poster', 'https://x/box'],
                              'detail': ['https://x/poster', 'https://x/box'], 'sku': ['https://x/box']}}
        item = {'id': 'FULL_MAIN_000', 'image_id': 'MAIN_000', 'pool': 'main', 'index': 0,
                'local': str(target), 'source_url': 'https://x/poster',
                'source_sha256': digest(target), 'evidence_ids': ['WM_POSTER']}
        reference = {'kind': 'main', 'index': 1, 'url': 'https://x/box',
                     'file': str(retained), 'content_sha256': digest(retained)}
        return product, item, reference

    def inspector(self, decorated=True):
        class Inspector:
            def inspect_deletion(self, *args, **kwargs):
                return {'ok': decorated, 'is_box': True, 'is_official': False,
                        'category': 'DECORATION', 'information_preserved': True,
                        'decorated_composite': decorated, 'retained_packaging_verified': True,
                        'evidence_ids': ['DUAL_FULL_IMAGE_REVIEW']}
        return Inspector()

    def test_authorized_composite_can_delete_while_retaining_real_box_photo(self):
        with tempfile.TemporaryDirectory() as directory:
            product, item, reference = self.fixture(directory)
            row = plan_deletion(directory, item, product, [reference], self.inspector(), decorated_refs=[reference])
            self.assertEqual(row['action'], 'DELETE_REDUNDANT')
            self.assertTrue(row['is_box'])
            self.assertTrue(row['checks']['decorated_composite'])
            self.assertTrue(row['checks']['retained_packaging_verified'])
            self.assertNotIn('non_box_deletion', row['checks'])
            validate_candidate(row)

    def test_plain_box_and_missing_retained_packaging_do_not_become_composites(self):
        with tempfile.TemporaryDirectory() as directory:
            product, item, reference = self.fixture(directory)
            self.assertIsNone(plan_deletion(directory, item, product, [reference], self.inspector(False), decorated_refs=[reference]))
            self.assertIsNone(plan_deletion(directory, item, product, [], self.inspector(), decorated_refs=[]))

    def test_ordinary_box_protection_remains(self):
        with tempfile.TemporaryDirectory() as directory:
            product, item, reference = self.fixture(directory)
            self.assertIsNone(plan_deletion(directory, item, product, [reference], self.inspector()))

    def test_two_composites_cannot_use_each_other_as_retained_material(self):
        from auto_deletions import plan_decorated_cleanup
        with tempfile.TemporaryDirectory() as directory:
            product, item, reference = self.fixture(directory)
            second = Path(directory)/'poster2.png'
            Image.new('RGB', (800, 800), 'yellow').save(second)
            product['images']['main'].insert(1, 'https://x/poster2')
            raw = [{'kind': 'main', 'index': 0, 'url': item['source_url'], 'file': item['local']},
                   {'kind': 'main', 'index': 1, 'url': 'https://x/poster2', 'file': str(second)},
                   dict(reference, index=2)]
            class Inspector:
                def inspect_deletion(self, source, context, **kwargs):
                    decorated = Path(source).name != 'box.png'
                    return {'ok': decorated, 'is_box': True, 'is_official': False,
                            'category': 'DECORATION' if decorated else 'PRODUCT',
                            'information_preserved': True, 'decorated_composite': decorated,
                            'retained_packaging_verified': decorated, 'evidence_ids': ['DUAL']}
            rows = plan_decorated_cleanup(directory, product, raw, Inspector())
            self.assertEqual(len(rows), 2)
            deleted = {row['source']['url'] for row in rows}
            self.assertTrue(all(ref['url'] not in deleted for row in rows for ref in row['source']['retained_references']))

    def test_full_fake_flow_prefers_whole_composite_deletion_and_excludes_title(self):
        from copy import deepcopy
        import json
        from unittest.mock import patch
        import test_full_audit_remediation_bridge as bridge
        from test_full_product_audit import FullProductAuditTests
        from full_product_audit import build_inventory
        from test_auto_decision import CONFIG
        from job_manager import JobManager, atomic_json
        from automation_policy import AutomationPolicy
        from candidate_quality import CandidateQualityGate
        from workflow_runner import run_automatic
        from execution_ledger import ExecutionLedger
        with tempfile.TemporaryDirectory() as directory:
            product, raw, reader, original_auditor, judge, template = bridge.FullAuditRemediationBridgeTests().fixture(directory)
            product['images']['detail'] = list(product['images']['main'])
            product['skus'][0]['id'] = None
            product['skus'][1]['id'] = None
            box = Path(directory) / 'green.png'
            Image.new('RGB', (800, 800), 'green').save(box)
            product['images']['main'].append('https://x/c')
            product['images']['detail'].append('https://x/c')
            product['images']['sku'] = ['https://x/b', 'https://x/c']
            product['skus'][1]['skuImageUrl'] = 'https://x/c'
            sources = {r['url']: r for r in raw}
            sources['https://x/c'] = {'file': str(box), 'url': 'https://x/c', 'ocr': [],
                                      'content_sha256': hashlib.sha256(box.read_bytes()).hexdigest()}
            raw[:] = [dict(sources[url], kind=pool, index=index) for pool in ('main', 'detail', 'sku')
                      for index, url in enumerate(product['images'][pool])]
            judge.results = FullProductAuditTests().decisions(build_inventory(product, raw))
            poster_hash = sources['https://x/a']['content_sha256']
            for row in judge.results['WM_' + poster_hash[:16]]['results']:
                row['confidence'] = .4
                row['abstain'] = True
            def auditor(pid, shop, output_dir, site):
                original_auditor(pid, shop, output_dir, site)
                atomic_json(output_dir/'audit_account.json', {'account_fingerprint': 'a'*64, 'status': 'VERIFIED'})
                atomic_json(output_dir/'audit_flags.json', {'pid': pid, 'summary': {'ocr_enabled': True},
                            'duplicates': [], 'anomalies': [{'type': 'title_prefix'}]})
            class Inspector:
                def inspect_deletion(self, source, context, **kwargs):
                    composite = hashlib.sha256(Path(source).read_bytes()).hexdigest() == poster_hash
                    return {'ok': composite, 'is_box': composite, 'is_official': False,
                            'category': 'DECORATION' if composite else 'PRODUCT',
                            'information_preserved': True, 'decorated_composite': composite,
                            'retained_packaging_verified': composite, 'evidence_ids': ['FULL_COMPOSITE']}
                def observe_image(self, path, context):
                    return dict(verified=True, clean=True, image_type='BOX' if Path(path).name == 'green.png' else 'FIGURE',
                                model='DW-ES09T', sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                                evidence_ids=['SKU_IMAGE'])
                def propose(self, *args):
                    raise AssertionError('A confirmed removable composite must not be cropped first')
            manager = JobManager(Path(directory)/'jobs')
            job = manager.create(1, 7, {'ai_requests': 100, 'full_resolution_images': 32, 'total_tokens': 200000},
                                 mode='auto_apply', templates_required=False)
            from template_applicability import snapshot
            snapshot(template, manager.directory(job['job_id']))
            config = deepcopy(CONFIG)
            config.update(delete_decorated_composites=True, allow_snapshot_sku_rows=True)
            config['allow_actions'].update(DELETE_REDUNDANT=True, SKU_ASSIGN=True, TITLE_REWRITE=False, BRAND_CODE=False)
            blobs = {r['url']: Path(r['file']).read_bytes() for r in raw}
            reader.saves = 0
            def save(pid, desired, **kwargs):
                reader.saves += 1
                product.clear(); product.update(deepcopy(desired))
            reader.save = save
            reader.fetch_image = lambda url: blobs[url]
            reader.readonly_client = lambda: reader
            protected = deepcopy(product['descriptionJson'])
            with patch('execution_ledger.ExecutionLedger', side_effect=lambda: ExecutionLedger(Path(directory)/'execution.sqlite')):
                result = run_automatic(manager, job, AutomationPolicy(config), writer=reader, auditor=auditor,
                                       judge=judge, quality_gate=CandidateQualityGate(Inspector()), full_audit_reader=reader)
            deferred = json.loads((manager.directory(job['job_id'])/'deferred_items.json').read_text())['items']
            self.assertEqual(result['status'], 'AUTO_VERIFIED', deferred)
            self.assertEqual(reader.saves, 1)
            self.assertEqual(product['images']['main'], ['https://x/b', 'https://x/c'])
            self.assertEqual(product['images']['detail'], ['https://x/b', 'https://x/c'])
            self.assertEqual(product['descriptionJson'], protected)
            deferred = json.loads((manager.directory(job['job_id'])/'deferred_items.json').read_text())['items']
            self.assertFalse(deferred)
