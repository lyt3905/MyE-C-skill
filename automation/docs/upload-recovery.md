# 上传失败与受限续办

上传接口与普通接口均正确处理后台地址末尾的 `/`，并保留后台部署子路径。上传采用真实图片 MIME、多部分表单，返回 URL 后核对图片字节；失败不会被当作商品已保存。

执行账本默认阻止未知写入任务被新任务覆盖。`ExecutionLedger.claim_after_rejected_upload` 仅供明确授权的续办调用，不是自动重试开关，也未作为通用 CLI 恢复分支开放。它要求原任务的首次上传明确返回 HTTP 400、没有成功上传收据、没有进入保存阶段，并将原 Job、计划、账本、账号、商品及当前状态绑定。`save_attempt.json`、`expected_after.json` 或 `apply_receipt.json` 任一存在都会拒绝此路径。

续办必须使用新 Job 和新授权，在同一账号锁内独立读取当前商品并核对状态摘要。方法将原 `APPLY_UNKNOWN` 账本记录追加到 `execution_rejected_upload_followups` 后，才为新任务预留执行；原 Job、响应、原上传收据和旧执行日志保持原样。调用方在新任务执行前使用 `verify_rejected_upload_proof` 再核验源证据。

超时、部分上传、证据变化、账号或状态不一致、任何商品保存阶段记录，以及旧 Job 重放，继续阻断。该路径不把未知保存改成成功，也不负责自动消除孤立上传资源。

相关回归：`tests/test_upload_base_join.py`、`tests/test_rejected_upload_followup.py`、`tests/test_auto_execution_ledger.py`、`tests/test_auto_recovery_policy.py`。全量离线测试入口：`python -B scripts/run_tests.py`。
