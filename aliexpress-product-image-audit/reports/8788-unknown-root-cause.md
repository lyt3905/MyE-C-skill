# 8788 UNKNOWN原因还原

已确认源码存在Prompt/Schema主要验证root，而全量消费者要求marks的契约错位。历史任务purpose另要求marks，因此实际输出有时带marks，不能把所有UNKNOWN解释成marks缺失。
在5097横幅样本中实际已有marks；v1还因营销文字待定类别、局部置信度不足返回UNKNOWN。其他样本包括root弃权、低于0.90及BOX/MIXED冲突。
矩阵中的baseline_first_return是原v1聚合器的首个返回条件；reason字段是新诊断契约指出的具体字段/区域问题。两者分开，不把新Schema缺项冒称历史模型违规。
已识别局部事实保持原值，旧输出没有覆盖声明、像素区域或维度观察时不补成完整结果。

| 任务 | 原v1首个触发条件 | 原因 |
|---|---|---|
| WM_20583cfb87a9ac7e | _watermark: mark validation | OWNER_UNPROVEN |
| IDENTITY_20583cfb87a9ac7e | 该v1首判没有发现UNKNOWN条件 | 见完整逐维度检查 |
| WM_f58ef0242d0737a4 | _strong: abstain | MODEL_ABSTAIN |
| IDENTITY_f58ef0242d0737a4 | 该v1首判没有发现UNKNOWN条件 | 见完整逐维度检查 |
| WM_e9a1233b0d4e4282 | _strong: abstain | MODEL_ABSTAIN |
| IDENTITY_e9a1233b0d4e4282 | _strong: confidence < 0.90 | LOW_CONFIDENCE |
| WM_4292661510e41155 | _strong: confidence < 0.90 | LOW_CONFIDENCE |
| IDENTITY_4292661510e41155 | _strong: confidence < 0.90 | LOW_CONFIDENCE |
| WM_b001256f37783043 | _strong: confidence < 0.90 | LOW_CONFIDENCE |
| IDENTITY_b001256f37783043 | _strong: confidence < 0.90 | LOW_CONFIDENCE |
| WM_0fd90100f20a2edc | _watermark: mark validation | LOW_CONFIDENCE |
| IDENTITY_0fd90100f20a2edc | _strong: confidence < 0.90 | LOW_CONFIDENCE |
