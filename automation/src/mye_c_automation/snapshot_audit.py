"""Sealed local input adapter for the existing V2 audit, with no site/writer."""
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from mye_c_automation.job_manager import JobManager, atomic_json


def _read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def _files(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


class SnapshotReader:
    def __init__(self, source, pid, shop):
        from mye_c_automation.v2_remediation import verify_audit
        self.source = Path(source).resolve()
        if not self.source.is_dir():
            raise ValueError('SNAPSHOT_SOURCE_NOT_FOUND')
        self.job = JobManager(self.source.parent).load(self.source.name)
        if (self.job['pid'], self.job['shop_id'], self.job.get('image_workflow')) != (pid, shop, 'v2'):
            raise ValueError('SNAPSHOT_CONTEXT_MISMATCH')
        self.product_snapshot = _read(self.source/'audit_product.json')
        self.inventory, _ = verify_audit(self.source, self.job)
        if not self.inventory['contents']:
            raise ValueError('SNAPSHOT_NO_IMAGES')
        account = _read(self.source/'audit_account.json')
        if not self.job.get('account_fingerprint') or account.get('account_fingerprint') != self.job['account_fingerprint']:
            raise ValueError('SNAPSHOT_ACCOUNT_UNBOUND')
        self.images = {}
        for digest, content in self.inventory['contents'].items():
            path = Path(content['file']).resolve()
            if not path.is_relative_to(self.source) or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError('SNAPSHOT_IMAGE_CHANGED')
            for url in content['urls']:
                if url in self.images and self.images[url][1] != digest:
                    raise ValueError('SNAPSHOT_URL_CONFLICT')
                self.images[url] = (path, digest)

    def current_shop(self):
        return self.job['shop_id']

    def account_fingerprint(self):
        """Historical bound identity, not a new online login."""
        return self.job['account_fingerprint']

    def product(self, pid):
        if pid != self.job['pid']:
            raise ValueError('SNAPSHOT_CONTEXT_MISMATCH')
        return deepcopy(self.product_snapshot)

    def download(self, url, destination):
        if url not in self.images:
            raise ValueError('SNAPSHOT_IMAGE_UNAVAILABLE')
        path, digest = self.images[url]
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError('SNAPSHOT_IMAGE_CHANGED')
        Path(destination).write_bytes(data)

    def audit(self, pid, shop, *, output_dir, site):
        from mye_c_automation.full_product_audit import download_only
        return download_only(pid, shop, output_dir=output_dir, site=self, downloader=self.download)


def audit_snapshot(source_job, pid, shop, *, instruction, config_dir=None, data_dir=None):
    from mye_c_automation.automation_policy import AutomationPolicy
    from mye_c_automation.full_product_audit import run_full_audit
    from mye_c_automation.model_config import load_config
    from mye_c_automation.one_command import _runtime_environment, _scoped_path
    from mye_c_automation.paths import config_root, data_root, initialize_data
    if not isinstance(instruction, str) or not instruction.strip():
        raise ValueError('SNAPSHOT_NEW_INSTRUCTION_REQUIRED')
    source = Path(source_job).expanduser().resolve()
    destination = data_root(data_dir)
    if destination.is_relative_to(source):
        raise ValueError('SNAPSHOT_OUTPUT_OVERLAP')
    reader = SnapshotReader(source, pid, shop)
    before = _files(source)
    config = config_root(config_dir)
    policy = AutomationPolicy.load(_scoped_path(config, pid, 'automation.local.json'))
    policy.authorize(pid, shop, [], execution=False)
    profile = load_config(config/'model.local.json')
    root = initialize_data(destination)
    with _runtime_environment(config, root):
        manager = JobManager(root/'jobs')
        job = manager.create(pid, shop, dict(ai_requests=policy.config['max_ai_requests_per_job'],
            full_resolution_images=10000, site_save=0), mode='audit', image_workflow='v2',
            model_config=profile, model_budget=dict(mode='RECORD_ONLY', usage_source='GATEWAY_REPORTED_UNVERIFIED'))
        target = manager.directory(job['job_id'])
        origin = dict(data_origin='SEALED_PRIOR_JOB', source_job_id=reader.job['job_id'],
            source_directory=str(source), source_files=before, instruction=instruction,
            account_verification='HISTORICAL_BINDING_NOT_LIVE_LOGIN', pid=pid, shop=shop,
            read_only=True, site_reads=0, site_save_calls=0, upload_calls=0)
        atomic_json(target/'snapshot_origin.json', origin)
        try:
            audit = run_full_audit(manager.root, pid, shop, reader, manager=manager, job=job, auditor=reader.audit)
        finally:
            if _files(source) != before:
                raise ValueError('SNAPSHOT_SOURCE_CHANGED')
        decisions = _read(target/'full_ai_judgements.json')
        metrics = _read(target/'full_ai_metrics.json')
        result = dict(status='AUDITED' if audit['audit_complete'] else 'REVIEW_REQUIRED',
            job_id=job['job_id'], pid=pid, shop=shop, data_origin='SEALED_PRIOR_JOB',
            source_job_id=reader.job['job_id'], source_unchanged=True, read_only=True,
            site_reads=0, site_save_calls=0, upload_calls=0, audit_status=audit['audit_status'],
            unique_images=len(decisions), decisions=dict(Counter(r['decision'] for r in decisions.values())),
            unresolved_count=audit['unresolved_count'], model_requests=metrics['requests'],
            evidence_directory=str(target), report=str(target/'report.md'),
            origin_sha256=hashlib.sha256((target/'snapshot_origin.json').read_bytes()).hexdigest(),
            semantic_review_only=True, remediation_status='NOT_RUN')
        atomic_json(target/'snapshot_result.json', result)
        return result
