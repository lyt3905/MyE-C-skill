# token-opt-v2.1 状态报告

本轮未执行任何生产写站、账户创建或 ACL 修改。离线测试不能证明真实账户隔离及审核质量。

先离线备份原代码及 Job 数据；部署独立 Agent/Executor SID，程序和密钥目录执行最小权限；运行部署审查，未验证项必须阻断。配置显式只读会话及 HTTPS；启用 Shadow，不写站。

复核：review-submit 绑定 Job/PID/Shop 和 evidence_sha256；未处理项保持 NEEDS_REVIEW。计划生成后 live-dry-run，再由受验证 SID 的 IPC 携带独立票据执行。执行请求必须指定当前 Job/plan；失败结果持久化。

回滚：停用 Executor 服务及新票据签发，保留 nonce/执行记录；恢复备份代码仅运行 v1 只读历史解析。旧 v1 写站永久拒绝，不得通过回滚重开绕过路径。真实商品回滚需根据写前快照生成新受审计划并另行授权，当前未执行。
