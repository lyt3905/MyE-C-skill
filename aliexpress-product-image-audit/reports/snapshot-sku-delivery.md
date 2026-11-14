# 自动整改目标阶段交付：无ID SKU定位与5097单件预演

2026-11-14最新结果：用户明确启动后，Shop7/PID5097已实际保存1次、上传0次，修复“无盒”SKU误用盒图。程序双模型写后检查及另外一次独立GET/原始字节下载均通过；有盒行及其他保护字段保持原样。已完成本目标要求的至少一件真实商品单项整改闭环。商品整体仍为PARTIALLY_AUTO_FIXED，其余9项保留，不代表全商品或批量审核通过。详见[snapshot-canary-5097-result.md](snapshot-canary-5097-result.md)。

## 具体整改

Shop7 / PID5097（Dr. Wu DW-ES09T）。两规格原来共用盒子照片；“无盒”规格应使用本体图。

最新方案只修改第0行“no retail box”的skuImageUrl，并将已有本体图加入images.sku；“with retail box”行完整保留。使用商品当前已有的详情第4张本体图，不上传、不擦图、不裁图、不删除图片，不改标题、Description采集内容、价格输入、库存、重量或状态。

预演：JOB_754f9da4704b4f1f9f3536a5fe61241b / DRY_RUN_PASSED。计划SHA256：d8fe45dd9fbace9067a9e9d3b70c76e938393ce6143745e4aa342354f8598379。

候选本体图SHA256：4292661510e41155463451b49d871611c08827bdb1b6dd0701a484eb4c05e8b7。两模型独立质量判定置信度0.95和0.90，均MATCH，身份、包装、干净程度及保护内容检查通过；原有摄影署名保留。实际新下载的字节哈希与验证证据相同。

实际真实执行：上传0次、保存1次、翻译0次、状态操作0次。写后重新GET及下载验证通过。其余9项保留，不能把单项整改成功称为整商品审核全部通过。

![无盒SKU整改前后](snapshot-canary-5097-preview.jpg)

## 源码修改

- snapshot_sku.py：按完整源快照及原始行哈希定位无ID SKU，限定明确的1～2行有盒/无盒规格；不创建假SKU ID。
- sku_assignment.py：显式允许时生成快照行分配；不确定的现有有盒引用先保留；完全相同SHA的多URL只算一份候选，不将不同姿态或不同SHA合并。
- automation_policy.py：新增可选allow_snapshot_sku_rows布尔配置，默认关闭。
- semantic_remedies.py、workflow_v2_pipeline.py：连接行定位及逐行暂缓记录，保持身份、颜色、包装与套装保护。
- plan_compiler.py、plan_v2.py、final_state.py：编译、校验、模拟快照行分配，拒绝重复行、源行变化和未授权字段。
- auto_workflow.py：逐行回读、下载并核对已验证字节；未授权裁剪/擦除时不调用几何模型。
- executor/local.py、executor/service.py：执行边界再次检查快照行权限。
- executor/site_write_client.py：写后下载使用与审核下载器一致的公开图片请求头，修复实测403；不附带站点Cookie或认证头，保留协议与大小限制。
- 三份JSON Schema及新增回归测试同步更新。

## 验证记录

每个修复均先运行失败用例，再修改实现。失败阶段包括：缺失快照行能力、整条Fake工作流不接受新策略、无ID行失败位置无法区分、未开启几何动作仍请求模型、有盒引用被多余修改、相同字节不同URL误判为多候选，以及回读器不带公开图片请求头。原终端输出在本聊天；最终测试完整日志为snapshot-sku-final-delivery-full.log。

最终完整回归507项全部通过，252.044秒，退出码0；compileall通过，242份应用/配置/测试文件的当前源码清单逐项哈希匹配。完整日志snapshot-sku-final-delivery-full.log，状态snapshot-sku-final-delivery-status.json。早期501、503、504、505项通过记录分别保留，不替代最终结果。

Fake闭环证据：snapshot-sku-fake-rollback.json验证SKU分配、回读及恢复原快照；snapshot-goal-fake-upload-rollback.json另验证上传1次/保存1次/独立下载后再受控恢复，均无真实站点或模型调用。snapshot-canary-guard-check.json验证真实执行包装器拒绝额外字段、目标变化、上传和翻译。

## 模型用量

本目标阶段累计65次请求，实报236,102 Token，全部用量已知：

| 运行 | 请求 | Token | 结果 |
|---|---:|---:|---|
| 6个人工标签样本的配对区域证据对照 | 24 | 57,783 | 不足以推广裁图默认输入 |
| 5097第一次删除预演 | 12 | 32,706 | 暂缓，未进入删除验证 |
| 5097快照SKU首次预演 | 27 | 133,019 | 两行修改预演通过，后续收紧 |
| 两次收紧方案复核 | 0 | 0 | 复用原生已验证缓存；预算为0，未重置原Job预算 |
| 用户启动的5097真实Canary | 2 | 12,594 | 实际保存1次，写后双模型检查及独立下载通过 |

不含此前4932的80,580 Token或更早历史运行。一次已报用量的JSON解析失败计入真实消耗；没有把失败当作零，也没有隐藏为重试成功。生产Canary实际新增用量单独记录，没有重做标签对照；执行后专用策略自动关闭。

## 交付链接

- [功能覆盖矩阵](snapshot-sku-coverage.md)
- [Windows验收与回滚](snapshot-sku-windows.md)
- [真实源状态与下载证据](snapshot-canary-5097-readback.json)
- [图片判断对照结果](auto-remedy-goal-crop-calibration.md)
- [SKU网站契约核查](auto-remedy-goal-sku-contract.md)
- [当前源码清单](v1.3-current-source-manifest.json)

## 未验证与未完成

真实SKU整组保存契约已在本例的两行无ID、有盒/无盒数据上验证。该证据不覆盖任意SKU结构或后台所有行为。批量自动整改、所有水印样式、未知包装及复杂套装仍不放行。摄影/原厂保护样本数量不足以证明批量准确率门槛；没有降低规则或伪造标签。真实回滚只生成只读预演，未实际执行恢复；Fake已验证恢复链路。
