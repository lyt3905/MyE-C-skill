# Phase 4 executor protocol

`ExecutorService(authorization, writer, evidence_root).execute(plan, ticket, dry_run=True)` is network-free until a trusted deployment injects a writer and explicitly selects live execution. Never pass Agent-controlled secrets. `Authorization(secret, nonce_database)` requires an external protected secret and durable nonce database. `SiteWriteClient(site)` reuses existing Site.save final state verification, preserving weight and identity.

Plans use token-opt-plan/v2 with exact top-level fields in plan_v2.validate_plan. desired contains only titleEn/images/descriptionJson/brandId. review must be {status: RESOLVED}. Evidence refs use relative path + SHA256. post_actions accepts uploads (path, sha256, pool, index) and translate_title boolean. Upload destinations must exist in desired.images. Authorization binds the complete plan hash, job, PID, shop, expiration, nonce, operation set, max_site_saves=1, max_upload_calls and max_translate_calls (0..2). Service currently performs one translation call when requested. Upload success followed by failure may leave orphan resources; no automatic rollback is attempted.

Legacy apply_token_plan CLI --apply is disabled before Site construction; v1 library remains for regression and archived rollback. This is routing enforcement, not OS isolation. A separate Windows account, protected credential files, network restrictions and authenticated IPC must be deployed before production. No privileged server is enabled by this change.

## 本次离线补齐（2026-11-12）
- 已新增真实Windows命名管道服务与JSON client；显式SID DACL、拒绝远程、首实例占用保护、64KiB帧上限、读超时、默认禁写。
- workflow_runner.py executor-request --address PIPE --request REQUEST.json 可显式提交审核后计划；不会生成或签发票据。
- 生产Site使用显式凭据文件与严格HTTPS/系统CA校验，导入不触发凭据发现；fake模式无站点连接。
- 子进程测试验证无票据、计划变更、dry-run全部零保存；有效票据一次保存；重放拒绝。
- 部署审查入口见 ../executor-ipc.md 与 ../../deploy/review-executor-deployment.ps1。未创建用户、未改ACL、未安装服务、未真实写站。
- 安全前提仍需管理员落实隔离账户/保护代码解释器及配置密钥状态目录，独立审批端保管签名密钥，可信站点证书。配置中的deployment_verified是人工部署声明，不是自动ACL证明。
