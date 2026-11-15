# V2 离线准确率评估

复用 scripts/shadow_evaluate.py。此工具只读取本地 JSONL 和图片，不调用模型或站点。旧 --quality 和默认二元比较模式保留。

## 数据准备

work/v2-evaluation-20261115/datasets/real-labels.empty.jsonl 是空文件，必须由实际审核输出及独立人工标注填充，不能复制 synthetic-example.jsonl 当真实数据。每行一个对象，无 Description 或其他商品正文。

必填字段：schema 固定 v2-accuracy-sample/v1；image_sha256 为原图片字节 SHA256；image_type 为 MAIN/DETAIL/SKU；evidence_kind 为 FAKE/REAL_SHADOW；human_confirmed 为布尔；prediction_action 为 KEEP/DELETE/REMOVE_TEXT/AI_REGENERATE/REVIEW；confidence 为0到1有限数；abstain 为布尔。

可选字段：label_source（独立标注来源，存在真值或人工确认时必填）、ground_truth_action（五动作或null）、ground_truth_retail_box（PRESENT/ABSENT/UNKNOWN/null）、prediction_retail_box（PRESENT/ABSENT/UNKNOWN/UNCERTAIN）、repair_pass、severe_error、sku_selection_correct（三者为布尔或null；REMOVE_TEXT 的 repair_pass 必须由人工同时确认区域定位、文字处理效果和关键结构无损，AI_REGENERATE 必须确认商品身份及结构）、source_image（本地原图路径）。REAL_SHADOW 必须有可解码图片，实际字节SHA必须匹配。相对图片路径按运行工作目录解释，建议使用绝对路径。

同SHA跨主图/详情/SKU只计一份独立样本，评分字段冲突则拒绝。人工标签和图片绑定仅证明输入一致性，不认证标注人或供应商身份。FAKE 永不计入真实门槛。真实数据未人工确认时真值不参与评分。低于0.80或弃权转为REVIEW；UNKNOWN包装不转换为无盒。

## 运行

```powershell
..\ae-img-audit\.venv\Scripts\python.exe scripts/shadow_evaluate.py work/v2-evaluation-20261115/datasets/real-labels.empty.jsonl --v2 --output reports/v2-evaluation-empty-real.json
```

REMOVE_TEXT 的项目修复通过率通过 --remove-text-min-pass-rate 显式传入；未配置时该门槛不通过，不擅自预设业务比例。示例数据仅演示格式和评分，不设置真实门槛。

## 结果含义

按五动作统计建议数、标注数、精确率、严重错误、修复通过率；REVIEW单独统计暂缓率，不计自动动作准确。包装有盒误判无盒、无盒误判有盒分别统计；SKU有盒/无盒分组统计。

无数据时 NOT_EVALUATED；仅Fake时 SYNTHETIC_ONLY。无分母的比率为null。自动动作至少30份独立真实人工标注；DELETE精确率至少98%、严重错误0；REMOVE_TEXT需全部修复结果及显式通过率；AI_REGENERATE需全部修复成功且无严重错误。包装/SKU额外采用每组30份已决定/已复核且无观察到错误的保守统计检查，不代表总体错误率保证。

statistical_gates_met 只代表当前输入的统计检查。release_authorized 与 real_provenance_independently_verified 始终false；即使统计通过，也不授权真实模型、Shadow、Canary或生产写入。仍需分别完成真实来源验证、运行范围授权、能力配置及阶段验收。

## 已恢复的历史人工标签

reports/v2-recovered-human-labels.json记录47份已验证原图SHA的旧人工标签，其中Q01–Q24全部24份。数据在当前work/v2-local-repair-recovery任务目录的reused-human-labels.jsonl与q01-q24-human-labels.jsonl；这是标签专用格式，须按SHA与当前模型输出匹配后再评分，不能直接当作带预测的--v2样本。水印二元标签不自动推导五动作、包装或SKU标签；明确整张删除的指令保留为DELETE动作真值。旧图与标签可复用，不重复标注、不重复计SHA，不把旧模型预测当当前模型预测。

## 原生读取旧标签库

--label-registry reports/v1.3-confirmed-label-registry.json 仅与 --v2 合用。无需先转换reused-human-labels.jsonl；后者保留为审阅用导出数据。按原图SHA验证和去重后，只有明确DELETE指令填入动作真值；二元水印仅显示在label_registry库存/匹配明细，不推为KEEP。匹配动作不会把未人工确认的严重错误、修复结果、包装/SKU字段一起升级为真值。

输入可为空，此时报告NOT_EVALUATED并显示标签库存和缺预测数；不会补造预测。真实/Fake分别统计，Fake不能减少缺少真实预测的库存。库存包含注册表文件SHA和各匹配确认编号；可用标签数与已评估动作样本数分别报告。

实际输出 reports/v2-registry-current-predictions.json：47份标签，匹配3份真实水印阴性标签R01/R05/R06，44份缺当前预测；动作真值未匹配，精确率仍null。旧标签库来源与源图片未改变，不能把三份水印真值当成完整五动作标注。
