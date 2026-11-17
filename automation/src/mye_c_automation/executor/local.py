"""Confirmed local execution with a durable no-retry journal."""
import json
from pathlib import Path
from mye_c_automation.executor.service import ExecutorService
from mye_c_automation.job_manager import atomic_json
from mye_c_automation.plan_v2 import plan_hash, planned_upload_count

class LocalExecutor:
    def __init__(self, writer, evidence_root, checker=None, automation_policy=None, budget=None, before_remote_write=None):
        self.writer = writer
        self.checker = checker
        self.root = Path(evidence_root)
        self.automation_policy=automation_policy
        self.budget=budget
        self.before_remote_write=before_remote_write

    def recover_readback(self,plan):
        """Observe an uncertain save. This method has no upload/save/translate path."""
        from mye_c_automation.plan_v2 import validate_plan
        from mye_c_automation.product_state import canonical_state_hash, diff_state, saved_state_matches
        plan=validate_plan(plan)
        journal=json.loads((self.root/'local_execution.json').read_text(encoding='utf-8'))
        if any(journal.get(k)!=v for k,v in dict(job_id=plan['job_id'],pid=plan['pid'],shop=plan['shop'],plan_sha256=plan_hash(plan)).items()):
            raise ValueError('RECOVERY_BINDING_MISMATCH')
        current=self.writer.product(plan['pid'])
        ExecutorService(None,self.writer,self.root)._identity(current,plan)
        expected_path=self.root/'expected_after.json'
        expected=json.loads(expected_path.read_text(encoding='utf-8')) if expected_path.exists() else None
        source_path=self.root/'before.json'
        if not source_path.exists():source_path=self.root/'audit_product.json'
        source=json.loads(source_path.read_text(encoding='utf-8')) if source_path.exists() else None
        if source is not None and canonical_state_hash(source)!=plan['precondition']['state_sha256']:
            raise ValueError('RECOVERY_SOURCE_BINDING_MISMATCH')
        if expected is not None and (plan.get('post_actions') or {}).get('translate_title'):
            expected['titleTranslationZh']=current.get('titleTranslationZh')
        outcome='MATCHED' if expected is not None and saved_state_matches(expected,current,source=source) else 'NOT_OBSERVED' if canonical_state_hash(current)==plan['precondition']['state_sha256'] else 'DRIFT'
        result={'write_outcome':outcome,'read_only':True,'retry_save_allowed':False,'status':'CONTENT_REVIEW_REQUIRED' if outcome=='MATCHED' else 'APPLY_UNKNOWN','site_save_calls':0,'upload_calls':0,'translate_calls':0,'status_calls':0,'changes':diff_state(expected,current) if expected is not None else None}
        atomic_json(self.root/'recovery_readback.json',result)
        atomic_json(self.root/'recovery_after.json',current)
        return result

    def execute_auto(self, plan, policy):
        if (plan.get('post_actions') or {}).get('sku_row_assignments') and policy.config.get('allow_snapshot_sku_rows') is not True:
            raise ValueError('SNAPSHOT_SKU_ASSIGNMENT_NOT_AUTHORIZED')
        if plan.get('schema')!='token-opt-plan/v3' or plan['automation']['policy_sha256']!=policy.sha256:
            raise ValueError('AUTOMATION_POLICY_CHANGED_OR_MISSING')
        policy.authorize(plan['pid'],plan['shop'],plan['automation']['actions'],uploads=planned_upload_count(plan))
        account=plan.get('precondition',{}).get('account_fingerprint')
        if callable(getattr(type(self.writer),'account_fingerprint',None)) and not account:
            raise ValueError('ACCOUNT_BINDING_REQUIRED')
        if account:
            for name in ('job.json','audit_account.json','dry_run.json'):
                path=self.root/name
                if not path.is_file():raise ValueError('ACCOUNT_BINDING_EVIDENCE_MISSING: '+name)
                record=json.loads(path.read_text(encoding='utf-8'))
                if record.get('account_fingerprint')!=account:raise ValueError('ACCOUNT_BINDING_MISMATCH: '+name)
                if name=='dry_run.json' and (record.get('plan_sha256')!=plan_hash(plan) or record.get('live') is not True):
                    raise ValueError('ACCOUNT_PREVIEW_BINDING_MISMATCH')
        self.automation_policy=policy
        owned=self.budget is None
        if owned:
            from mye_c_automation.budget_manager import BudgetManager
            self.budget=BudgetManager({'site_save':1,'translate_title':2,'uploads':policy.config['max_uploads_per_job']},self.root/'auto_write_budget.sqlite')
        try:
            return self.execute(plan,dict(confirmed=True,job_id=plan['job_id'],pid=plan['pid'],shop=plan['shop'],plan_sha256=plan_hash(plan)))
        finally:
            if owned:self.budget.close();self.budget=None

    def retry_translation(self,plan,policy):
        """One durable translation retry; never calls upload or save."""
        from copy import deepcopy
        from mye_c_automation.plan_v2 import validate_plan
        from mye_c_automation.product_state import canonical_state_hash, saved_state_matches
        from mye_c_automation.account_coordination import account_lock, account_key
        from mye_c_automation.budget_manager import BudgetManager
        plan=validate_plan(plan)
        if plan['schema']!='token-opt-plan/v3' or plan['automation']['policy_sha256']!=policy.sha256 or not (plan['post_actions'] or {}).get('translate_title'):
            raise ValueError('TRANSLATION_RETRY_NOT_AUTHORIZED')
        policy.authorize(plan['pid'],plan['shop'],plan['automation']['actions'])
        pending=json.loads((self.root/'translation_pending.json').read_text(encoding='utf-8'))
        journal=json.loads((self.root/'local_execution.json').read_text(encoding='utf-8'))
        if journal.get('plan_sha256')!=plan_hash(plan) or pending.get('pid')!=plan['pid'] or pending.get('titleEn')!=plan['desired'].get('titleEn'):
            raise ValueError('TRANSLATION_RETRY_BINDING_MISMATCH')
        with account_lock(account_key(self.writer,self.root.parent)):
            current=self.writer.product(plan['pid']);ExecutorService(None,self.writer,self.root)._identity(current,plan)
            expected=json.loads((self.root/'expected_after.json').read_text(encoding='utf-8'))
            source_path=self.root/'before.json'
            source=json.loads(source_path.read_text(encoding='utf-8')) if source_path.exists() else None
            expected['titleTranslationZh']=current.get('titleTranslationZh')
            if not saved_state_matches(expected,current,source=source):raise ValueError('STATE_DRIFT_BEFORE_TRANSLATION')
            retry=self.root/'translation_retry.json'
            with retry.open('x',encoding='utf-8') as stream:
                json.dump({'plan_sha256':plan_hash(plan),'state':'TRANSLATION_PENDING'},stream)
                stream.flush()
                import os
                os.fsync(stream.fileno())
            budget=BudgetManager({'site_save':1,'translate_title':2,'uploads':policy.config['max_uploads_per_job']},self.root/'auto_write_budget.sqlite')
            result={'translation_status':'TRANSLATION_PENDING','site_save_calls':0,'upload_calls':0,'translate_calls':0,'status_calls':0}
            try:
                budget.reserve('translate_title');policy.verify_current()
                result['translate_calls']=1
                self.writer.translate(plan['pid'],plan['desired']['titleEn'])
                after=self.writer.product(plan['pid']);ExecutorService(None,self.writer,self.root)._identity(after,plan)
                expected['titleTranslationZh']=after.get('titleTranslationZh')
                if not after.get('titleTranslationZh') or not saved_state_matches(expected,after,source=source):raise ValueError('TRANSLATION_READBACK_FAILED')
                result['translation_status']='TRANSLATED'
            except Exception as exc:result['error']=type(exc).__name__+': '+str(exc)
            finally:budget.close()
            atomic_json(retry,result)
            return result

    def execute(self, plan, confirmation=None, dry_run=False):
        service = ExecutorService(None, self.writer, self.root)
        service.execute(plan, dry_run=True)
        if dry_run:
            return {'dry_run': True, 'site_save_calls': 0, 'upload_calls': 0}
        expected = dict(confirmed=True, job_id=plan['job_id'], pid=plan['pid'], shop=plan['shop'], plan_sha256=plan_hash(plan))
        if confirmation != expected:
            raise ValueError('explicit bound confirmation required')
        journal = self.root / 'local_execution.json'
        # Exclusive create happens before any write, including uploads. Crashes never reopen apply.
        with journal.open('x', encoding='utf-8') as stream:
            json.dump(dict(expected, state='RESERVED'), stream)
            stream.flush()
            import os
            os.fsync(stream.fileno())
        class Confirmed:
            def consume(self, ticket, candidate):
                if ticket != expected or plan_hash(candidate) != expected['plan_sha256']:
                    raise ValueError('confirmation changed')
        side_effect_started=False
        def begin_side_effect():
            nonlocal side_effect_started
            if side_effect_started:return
            # Set before invoking the durable external guard: any ambiguous guard failure stays closed.
            side_effect_started=True
            if self.before_remote_write:self.before_remote_write()
            atomic_json(journal,dict(expected,state='APPLY_UNKNOWN'))
        try:
            from mye_c_automation.product_state import canonical_state_hash
            current = self.writer.product(plan['pid'])
            service._identity(current,plan)
            if canonical_state_hash(current) != plan['precondition']['state_sha256']:
                raise ValueError('STATE_DRIFT')
            if not plan['desired'] and not plan['post_actions']:
                result = dict(dry_run=False, site_save_calls=0, upload_calls=0, verification_ok=True)
            else:
                result = ExecutorService(Confirmed(), self.writer, self.root, budget=self.budget, automation_policy=self.automation_policy,before_remote_write=begin_side_effect).execute(plan, ticket=expected, dry_run=False)
            from mye_c_automation.check import verify_snapshot
            after = self.writer.product(plan['pid'])
            if self.checker:checked=self.checker(after)
            elif (plan.get('post_actions') or {}).get('main_reference_cleanup'):
                from mye_c_automation.main_preprocessing import verify_snapshot as verify_main_snapshot
                checked=verify_main_snapshot(current,plan,after)
            elif (plan.get('post_actions') or {}).get('reviewed_detail_deletions'):
                from mye_c_automation.reviewed_images import verify_reviewed_snapshot
                checked=verify_reviewed_snapshot(self.root,plan,after)
            else:
                from mye_c_automation.main_preprocessing import count_exception,verify_receipt
                if plan['precondition'].get('main_count_preflight'):verify_receipt(self.root,plan)
                checked=verify_snapshot(after,before=current,allow_existing_main_excess=count_exception(current,plan))
            atomic_json(self.root / 'final_check.json', checked)
            if not checked['ok']:
                raise ValueError('final check failed')
            result.update(apply_status='APPLY_MATCHED', structure_status='STRUCTURE_CHECKED', content_review_status='NOT_VERIFIED', verification_status='STRUCTURE_CHECKED', job_id=plan['job_id'], plan_sha256=plan_hash(plan), ok=True)
            if plan['precondition'].get('account_fingerprint'):result['account_fingerprint']=plan['precondition']['account_fingerprint']
            atomic_json(self.root / 'verification.json', dict(ok=True, final_check=checked))
            atomic_json(self.root / 'apply_receipt.json', result)
            atomic_json(journal, dict(expected, state='STRUCTURE_CHECKED', receipt=result))
            return result
        except Exception as exc:
            atomic_json(journal, dict(expected, state='APPLY_UNKNOWN' if side_effect_started else 'PREWRITE_FAILED', error=type(exc).__name__))
            if side_effect_started and (self.root/'expected_after.json').exists():
                try:self.recover_readback(plan)
                except Exception as read_error:atomic_json(self.root/'recovery_readback.json',{'write_outcome':'UNKNOWN','read_only':True,'retry_save_allowed':False,'error':type(read_error).__name__})
                if (plan.get('post_actions') or {}).get('translate_title') and not (self.root/'translation_pending.json').exists():
                    atomic_json(self.root/'translation_pending.json',{'pid':plan['pid'],'titleEn':plan['desired'].get('titleEn'),'error':'SAVE_RESPONSE_OR_VERIFICATION_UNKNOWN','retry_save_allowed':False})
            raise
