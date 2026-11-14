# 功能覆盖矩阵

| 要求 | 当前证据 | 状态 |
|---|---|---|
| 仅main/detail/sku及SKU引用；采集Description不参与整改 | 现有范围回归、最终全量日志、5097预演逐字段模拟 | 已验证本地与只读预演 |
| 0.90及双模型门槛 | 质量记录0.95/0.90；低置信度/弃权回归 | 未降低 |
| 原厂、摄影署名与包装盒保护 | 人工标签对照、原厂/删除回归、候选原像素及盒图原引用保留 | 已验证当前范围 |
| 无ID SKU安全定位 | 快照行SHA、整商品SHA、包装唯一性、默认关闭策略 | 本地与真实只读预演通过 |
| 源行重排、价格/属性变化拒绝 | test_snapshot_sku | Fake通过 |
| 不确定的有盒引用保持 | test_snapshot_sku与最终5097方案 | 通过 |
| 完全相同内容的多URL候选去重 | SHA完全一致回归；不同SHA的歧义仍拒绝 | 通过 |
| 编译与JSON Schema一致 | 实际Fake生成计划及候选通过Schema验证 | 通过 |
| 拒绝额外字段及越界动作 | snapshot-canary-guard-check.json；执行权限回归 | Fake通过 |
| 上传/保存/下载/恢复闭环 | snapshot-goal-fake-upload-rollback.json | Fake通过 |
| SKU修改/回读/恢复闭环 | snapshot-sku-fake-rollback.json | Fake通过 |
| 保存后行错位或改价停止、不重发 | test_snapshot_sku，APPLY_UNKNOWN及只读恢复记录 | Fake通过 |
| 图片站回读403修复 | test_site_readback_headers；真实新下载SHA/尺寸 | Fake与真实GET通过 |
| 可执行真实商品预演 | JOB_754f9da4704b4f1f9f3536a5fe61241b | DRY_RUN_PASSED |
| 真正线上保存与写后验证 | JOB_7d4f999a45e64242b2e405b47c1bfc18，保存1/上传0；独立GET与新下载SHA通过 | 本例已完成 |
| 批量生产、未知模板、复杂SKU | 无充分证据 | 未放行 |

测试通过不能替代真实验收。本例已取得实际单次保存和独立写后证据；批量仍未放行。原始两行方案保留为历史记录，实际执行仅第0行“无盒”整改方案。
