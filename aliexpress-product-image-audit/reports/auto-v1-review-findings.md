# 中期独立审查及修复记录

审查范围：当前工作区自动计划、质量门禁、执行器、Workflow；没有执行网络或生产写入。它是中期审查，不替代最终验收。

| 发现 | 修复证据 |
|---|---|
| 安全主图和DEFERRED详情共用URL时全局替换越界 | test_auto_reference_isolation.py：失败后通过；共享待办URL及描述引用保留 |
| 品牌单字段改动不能完成回读验证 | test_auto_brand_readback.py：按字段值与SOP映射验证，错值拒绝 |
| TITLE_REWRITE可夹带URL映射 | test_auto_action_scope.py：post action按授权动作范围校验 |
| 编译器信任输入checks和任意SHA | test_auto_evidence_binding.py：缺独立源/质量记录阻断；remedy_binding.py核验真实字节 |
| Live Dry-run未核当前Shop | test_auto_preview_identity.py：快照哈希相同但会话Shop错误仍拒绝 |
| SKU回读不核型号/字节 | test_auto_sku_readback_binding.py：干净但错型号/换字节均拒绝 |

后续仍需全目标独立验收，不能据此认定Phase 9完成。

## 最终定向复审及后续修复

复审未确认Critical缺陷，发现Important缺口：生成整改图未进入SKU候选；低分辨率盒照流程未接入；E07与E23证据不足。现补齐生成图SKU完整Fake流程、盒照完整Fake流程、实际audit_one入口E07混合分歧测试、E23空URL及上传哈希负例。复审撤回E23没有负例的判断（原索引遗漏）。

新增代码复审确认生成图观察RuntimeError会中断独立动作；已失败复现后修复为单项降级，test_auto_generated_sku覆盖，本次281项回归包含修复。复审为定向检查，不冒充全部需求审计。

最终自查：BOX验证文件未在执行证据refs中，新增Workflow断言RED后加入box_validation.json哈希绑定；新增执行器负例证明文件编译后变更在任何Writer调用之前拒绝。
