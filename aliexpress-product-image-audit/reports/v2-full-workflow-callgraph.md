# V2完整生产调用链

```mermaid
flowchart TD
  A[输入Shop ID和PID] --> B[workflow_runner / audit_one默认V2]
  B --> C[JobManager 新Job及预算账本]
  C --> D[full_product_audit.run_unified_audit]
  D --> E[download_only 主图/详情/SKU池/真实引用]
  E --> F[build_inventory SHA去重及全部来源位置]
  F --> G[JudgeClient DeepSeek和MiMo独立观察]
  G --> H[image_action_decision.decide 关键字段协调]
  H --> I[v2_remediation.prepare]
  I --> J[KEEP/DELETE/REMOVE_TEXT/AI_REGENERATE/REVIEW]
  J --> K[OpenCV或LaMa / 已配置Image Edit Adapter]
  K --> L[VisualQualityInspector 独立双模型复核]
  L --> M[select_v2 有盒/无盒及真实SKU ID]
  M --> N[现有compile_auto_plan和Plan]
  N --> O[现有LocalExecutor与SiteWriteClient]
  O --> P[上传去重/一次保存]
  P --> Q[重新读商品与图片二进制]
  Q --> R[v2_remediation.verify_content]
  R --> S[automatic_report 报告与账本]
```

read_only/full-audit停在只读视觉审核及报告，不调用整改上传。audit可生成本地候选与计划但不写站；dry_run只核对；auto_apply及新的run apply均受冻结策略及范围授权约束。单独apply还要求绑定Job/Plan的确认文件。恢复使用recover-readback/verify-saved，只读确认，不重发保存。

legacy仅为显式历史兼容，不是新正式V2路径；run内部遇到V2也转统一完整审核，禁止落入旧机器候选管线。分类唯一来源AI视觉，OpenCV/LaMa只处理像素与mask。所有模型与编辑适配器请求复用原JudgeClient/BudgetManager。
