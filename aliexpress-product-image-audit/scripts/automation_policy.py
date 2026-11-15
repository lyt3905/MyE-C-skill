"""Independent local preauthorization. CLI mode is never authorization."""
import hashlib
import json
from pathlib import Path

ACTIONS = frozenset('REPLACE_TWIN REPLACE_LOCAL CROP_BANNER BOX_NORMALIZE ERASE_LOCAL SKU_ASSIGN TITLE_REWRITE BRAND_CODE DELETE_REDUNDANT WEB_SEARCH DELETE REMOVE_TEXT AI_REGENERATE'.split())
MANDATORY = ('preserve_product_status','require_live_dry_run','require_post_write_readback',
             'require_content_validation','halt_batch_after_unknown_write','stop_on_global_integrity_error')

class AutomationPolicy:
    def __init__(self, config):
        self.config = json.loads(json.dumps(config))
        c = self.config
        if 'DESCRIPTION_URL_REMAP' in c.get('allow_actions',{}):raise ValueError('DESCRIPTION_PERMISSION_MIGRATION_REQUIRED: remove DESCRIPTION_URL_REMAP')
        known={'schema','enabled','mode','shop_allowlist','pid_allowlist','max_products_per_run','max_site_save_per_job','max_uploads_per_job','max_ai_requests_per_job','allow_actions','local_pool_index','allow_snapshot_sku_rows','delete_decorated_composites'}|set(MANDATORY)
        if set(c)-known:raise ValueError('UNKNOWN_AUTOMATION_POLICY_FIELD')
        if 'allow_snapshot_sku_rows' in c and type(c['allow_snapshot_sku_rows']) is not bool:raise ValueError('INVALID_SNAPSHOT_SKU_PERMISSION')
        if 'delete_decorated_composites' in c and type(c['delete_decorated_composites']) is not bool:raise ValueError('INVALID_COMPOSITE_DELETION_POLICY')
        if 'local_pool_index' in c and (type(c['local_pool_index']) is not str or not c['local_pool_index'].strip()):raise ValueError('INVALID_LOCAL_POOL_INDEX')
        if c.get('schema') != 'automation-policy/v1' or c.get('mode') != 'auto_apply':
            raise ValueError('INVALID_AUTOMATION_POLICY')
        for name in ('shop_allowlist','pid_allowlist'):
            if type(c.get(name)) is not list or any(type(v) is not int or v <= 0 for v in c[name]):
                raise ValueError('INVALID_ALLOWLIST: '+name)
        for name in ('max_products_per_run','max_site_save_per_job','max_uploads_per_job','max_ai_requests_per_job'):
            if type(c.get(name)) is not int or c[name] < (1 if name=='max_products_per_run' else 0):
                raise ValueError('INVALID_BUDGET: '+name)
        if c['max_site_save_per_job'] != 1 or any(c.get(k) is not True for k in MANDATORY):
            raise ValueError('REQUIRED_SAFETY_INVARIANT')
        if type(c.get('enabled')) is not bool or type(c.get('allow_actions')) is not dict:
            raise ValueError('INVALID_AUTOMATION_POLICY')
        if set(c['allow_actions'])-ACTIONS or any(type(v) is not bool for v in c['allow_actions'].values()):
            raise ValueError('UNKNOWN_ACTION')
        self.sha256 = hashlib.sha256(json.dumps(c,sort_keys=True,separators=(',',':')).encode()).hexdigest()

    @classmethod
    def load(cls, path):
        policy=cls(json.loads(Path(path).read_text(encoding='utf-8-sig')))
        policy.path=Path(path).resolve()
        return policy

    def verify_current(self):
        if hasattr(self,'path'):
            try: current=AutomationPolicy(json.loads(self.path.read_text(encoding='utf-8-sig')))
            except (OSError,ValueError,TypeError) as exc: raise ValueError('AUTOMATION_POLICY_CHANGED') from exc
            if current.sha256!=self.sha256: raise ValueError('AUTOMATION_POLICY_CHANGED')

    def permits(self, action):
        return action in ACTIONS and self.config['allow_actions'].get(action) is True

    def authorize(self, pid, shop, actions, *, product_count=1, uploads=0, ai_requests=0, execution=True):
        self.verify_current()
        c=self.config
        if type(execution) is not bool:raise ValueError('INVALID_EXECUTION_MODE')
        if execution and not c['enabled']: raise ValueError('AUTO_APPLY_DISABLED')
        if type(pid) is not int or type(shop) is not int or pid <= 0 or shop not in c['shop_allowlist']:
            raise ValueError('IDENTITY_NOT_AUTHORIZED')
        if c['pid_allowlist'] and pid not in c['pid_allowlist']: raise ValueError('PID_NOT_AUTHORIZED')
        if any(not self.permits(a) for a in actions): raise ValueError('ACTION_NOT_AUTHORIZED')
        for actual,limit in ((product_count,c['max_products_per_run']),(uploads,c['max_uploads_per_job']),(ai_requests,c['max_ai_requests_per_job'])):
            if type(actual) is not int or actual < 0 or actual > limit: raise ValueError('AUTOMATION_BUDGET_EXCEEDED')
        return self.sha256
