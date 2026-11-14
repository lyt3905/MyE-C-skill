# 主流程实施
run支持read_only/audit/dry_run/apply模式标签，所有模式先只读审核并停PLAN_READY或NEEDS_REVIEW；只有独立apply命令携具体confirmation才执行。本轮未执行生产操作。
唯一主入口workflow_runner：run→审核/证据/候选AI/policy/compiler；review-submit→绑定证据人工重编译；live-dry-run→真实GET状态比较和字段差异；apply→LocalExecutor→持久化一次save→回读→check.verify_snapshot→VERIFIED。
模板配置放Job目录template_config.json，按shop_id作用域调用wm_tpl.scan；HIT/SUSPECT/UNKNOWN进入AI候选。保留residcheck风格残差及高通拼图。残差数值不作为语义归属结论。
CLI示例：workflow_runner.py run --pid 123 --shop 7 --root work/v2；后续status/review-submit/live-dry-run/apply指定同一job。确认文件精确包含confirmed=true、job_id、pid、shop、plan_sha256。mode=apply标签不代表授权。
