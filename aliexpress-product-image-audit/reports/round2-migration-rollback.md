# 迁移回滚
保留plan/v2读取。旧review缺manifest拒绝，需重新审核；不静默授权KEEP。旧tests仅更新明确授权、真实PNG和新状态语义。未push、未删历史Job、未覆盖运行数据。源码包不含凭证/运行产物；回滚前先保存当前dirty diff，逐文件人工审阅恢复，不执行reset。
