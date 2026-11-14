# 单件审核恢复所需证据

只读整理，未请求模型、未修改预算或商品。源Job：JOB_93099438cf014a689846bc05469759ad。
6份不同图片、16个业务位置；14个审核任务预期28份模型结果，现存21份有效结果，仍缺7份。
其中部分请求被预算阻止，部分第二模型因前一步失败未进入调用，不能把“仅3条预算阻止事件”误写成“仅缺3份结果”。

4份图片精确匹配已有人工标签。人工确认仅用于对应的水印归属证据，不提升模型置信度，不替代型号、颜色、包装或SKU规则。

| 审核任务 | 有效模型结果 | 未完成原因 | 人工证据 |
|---|---|---|---|
| WM_20583cfb87a9ac7e | 2/2 | SUBMARK_OWNERSHIP_OR_CONFIDENCE_UNRESOLVED | 有，精确SHA匹配 |
| IDENTITY_20583cfb87a9ac7e | 2/2 | 该任务无缺失或低置信初筛项；最终以完整报告为准 | 有，精确SHA匹配 |
| WM_f58ef0242d0737a4 | 2/2 | MODEL_ABSTENTION, ROOT_CONFIDENCE_BELOW_0_90, SUBMARK_OWNERSHIP_OR_CONFIDENCE_UNRESOLVED | 有，精确SHA匹配 |
| IDENTITY_f58ef0242d0737a4 | 2/2 | ROOT_CONFIDENCE_BELOW_0_90 | 有，精确SHA匹配 |
| WM_e9a1233b0d4e4282 | 0/2 | HTTPError, MISSING_MODEL_RESPONSE | 有，精确SHA匹配 |
| IDENTITY_e9a1233b0d4e4282 | 2/2 | DECLARED_MODEL_NOT_EXACTLY_CONFIRMED | 有，精确SHA匹配 |
| WM_4292661510e41155 | 2/2 | ROOT_CONFIDENCE_BELOW_0_90, SUBMARK_OWNERSHIP_OR_CONFIDENCE_UNRESOLVED | 无 |
| IDENTITY_4292661510e41155 | 2/2 | ROOT_CONFIDENCE_BELOW_0_90 | 无 |
| WM_b001256f37783043 | 2/2 | SUBMARK_OWNERSHIP_OR_CONFIDENCE_UNRESOLVED | 无 |
| IDENTITY_b001256f37783043 | 2/2 | ROOT_CONFIDENCE_BELOW_0_90 | 无 |
| WM_0fd90100f20a2edc | 2/2 | ROOT_CONFIDENCE_BELOW_0_90, SUBMARK_OWNERSHIP_OR_CONFIDENCE_UNRESOLVED | 有，精确SHA匹配 |
| IDENTITY_0fd90100f20a2edc | 1/2 | BUDGET_EXCEEDED, MISSING_MODEL_RESPONSE, ROOT_CONFIDENCE_BELOW_0_90 | 有，精确SHA匹配 |
| SKU_ROW_000 | 0/2 | BUDGET_EXCEEDED, MISSING_MODEL_RESPONSE | 无 |
| SKU_ROW_001 | 0/2 | BUDGET_EXCEEDED, MISSING_MODEL_RESPONSE | 有，精确SHA匹配 |

## 预算差额证据

第一次未知用量返回之后，仍有3个在途成功响应实际返回用量，合计17,318 Token，恰好等于逐次记录与预算小计的差额。已保存每个item_id、模型和实报Token。
它们是已知用量的漏记，不是失败502的用量；补齐此差额也不能解除UNKNOWN。真实历史预算保持原样。

失败请求仍需网关/供应商提供含2次内部尝试的可信实际用量。当前没有可信凭证；本地请求存档目录仍不存在。

完整逐项观察、低置信文字的位置、人工确认来源及文件哈希：full-product-audit-recovery-inputs.json。
