# 当前调用链
workflow_runner.run → audit_one.audit → audit_product/raw/flags → workflow_v2_pipeline.pipeline → evidence_builder.build → JudgeClient.process_queue → policy_engine.evaluate → plan_compiler.compile_plan → plan.v2.json。
manual_review.submit → validate_review → compile_plan → PLAN_READY。
workflow_runner.live_dry_run → ExecutorService(dry_run=True) + reader.product → 状态哈希比较。
原executor-request → IPC → ExecutorService → writer.product/upload/save/product；本轮添加本地受确认执行入口。
check.py、residcheck.py、wm_tpl.py均存在，原调用完整性由专项检查并补测。
