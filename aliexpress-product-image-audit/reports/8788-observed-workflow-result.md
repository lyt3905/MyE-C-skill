# 六图自动审核真实运行与开发报告

本轮Shop7/PID5097固定六图的双模型审核流程已执行完毕，状态PIPELINE_COMPLETED_WITH_EXCEPTIONS。24个任务请求中23个响应通过新Schema，1个缺根级evidence_ids作为格式异常保留。
加上最初输出额度耗尽的失败，累计25次客户端模型调用。之后没有再调用模型。线上写入0、自动整改0。

## 结果与范围

两模型：deepseek-v4.1-flash / kimi-k3-1；地址http://127.0.0.1:8788/v1；观察模式OBSERVED_NO_TOKEN_CAP，HARD_CAP_GUARANTEED=false。严格预算模式未修改、仍不能宣称PREFLIGHT_PASS。
6份完整SHA图片映射16个主图/详情/SKU图池/引用位置，同内容只执行一对水印及一对身份判断。Description、价格、标题复核均未加入模型输入。
发现1处双模型确认的店铺水印，其他归属、区域匹配、型号或颜色不确定项继续UNKNOWN。每张图的图片类型和包装维度均有确定结果；整体身份仍UNKNOWN，未降低0.90或双模型规则。
最后一张的DeepSeek响应缺少根级evidence_ids；没有补造证据、置信度或假结果。Kimi的单模型观察保留，但不能成为双模型PASS。

| 图片SHA前缀 | 水印覆盖 | 水印复核 | 身份 | 确认异常 |
|---|---|---|---|---|
| 20583cfb87a9ac7e | COMPLETE | PARTIAL | UNKNOWN | 1 |
| f58ef0242d0737a4 | COMPLETE | UNKNOWN | UNKNOWN | 0 |
| e9a1233b0d4e4282 | COMPLETE | UNKNOWN | UNKNOWN | 0 |
| 4292661510e41155 | COMPLETE | UNKNOWN | UNKNOWN | 0 |
| b001256f37783043 | COMPLETE | UNKNOWN | UNKNOWN | 0 |
| 0fd90100f20a2edc | PARTIAL | UNKNOWN | UNKNOWN | 0 |

本轮只证明这6张既定证据图的图像审核执行链路能自动调用、校验、聚合和输出异常。未读取线上商品最新状态，未额外做SKU规格匹配，不宣称整件商品所有SOP均已审核通过。

## Token核验

逐条核对25条响应的输入、输出、总Token和缓存/推理子项包含关系，未发现合计或子项矛盾。缓存、推理明细没有再额外相加。
网关报告：输入93566 + 输出77284 = **170850 Token**，已含两条异常响应。当前修正批次24次报数158970，初次额度耗尽失败11880；不把复用父Job的21条再加一遍。

| 模型 | 客户端请求 | 异常 | 输入 | 输出 | 合计 |
|---|---|---|---|---|---|
| deepseek-v4.1-flash | 13 | 2 | 38729 | 65048 | 103777 |
| kimi-k3-1 | 12 | 0 | 54837 | 12236 | 67073 |

这些是网关返回报数，未核对供应商账单，不能证明原厂真实计费量；网关内部可能发生的额外转发也未独立核实。供应商账单Token字段保留null。未复用/修改历史预算，历史UNKNOWN仍保持原样。

## 修复与异常分支

1. 首调用输出8192全部用于推理，正文为空、finish_reason=length。保存原始失败，改为低推理强度+16384输出；修正后新Job运行，不覆盖失败证据。该有意修正后的重新运行计入累计25，不设自动重试循环。
2. 第21条根级evidence_ids缺失。停止原Job后，新子Job只处理从未发出的22～24条。父Job21条记录全部只读，错误项不重发、不改PASS。
3. 新的run_new入口会自动将单项格式异常交给这种补齐分支；正常流水线不需要人工逐项确认。网络、模型身份、来源或本地持久化错误仍停止；单次认领及持久化计数防止重复补齐。
4. 离线检查修复了报告在A响应无效时把B观察压入A槽位的问题；使用空的无效A槽位，B仍在B，聚合保持UNKNOWN。没有修改水印/身份Prompt、Schema、阈值或聚合规则，也没有为此再发模型请求。

## 源码、证据和可复现性

- 原433个历史文件全树哈希不变；原Job和full_audit_recovery入口均未运行。新父Job的全部文件也与子Job保存的parent_tree一致。
- 真实运行源码封存在8788-observed-executed-source.zip，与当时Job/source-versions.json逐文件核对后归档。
- 最终报告另用修正模型槽位显示后的报告处理源码离线重聚合；差异仅scripts/observed_audit.py，详见8788-observed-source-provenance.json。没有把最终代码SHA冒充请求时SHA。原始响应和规范化结果保持原样。
- 修改已有源码仅scripts/run_8788_real_validation.py的可选prepared-body参数；不提供参数时原行为保留。新增observed_audit.py、complete_observed_audit.py及两个测试文件。
- 精确本轮diff：8788-observed-workflow.patch，已在本轮基线副本通过git apply --check；改变文件及哈希见8788-observed-change-manifest.json。
- 本地分支codex/8788-contract-local-fix-20261114；未提交/推送、未触碰其他项目改动。

## 测试与视觉检查

最终全量646项通过，失败0、错误0；新增25项。运行ID 0690a0a0c78b4631aaffc53a82647a62，耗时818.0秒（含准备）。
测试进程禁止URL/TCP外网，捕获尝试0；其真实模型调用0。已授权的25次真实联调由单独进程执行，未混入Fake测试统计。
初轮12项Fake通过；输出额度/HTTP实际请求体/自动异常补齐/请求去重/重复续跑/模型A缺失归属均有回归。中间636项全量通过的日志独立保存；因实际联调和报告缺陷而停止的中间套件不作为最终通过证明。
最终测试前后源码哈希一致，交付时再次核对；旧621项和预算/Schema回归全部保留。
六张区域对照图已由开发助手查看，详见8788-observed-visual-review.md。摄影署名框存在长短差异，包装小字分组存在差异；UNKNOWN未抹去。没有独立人工真值，不能给准确率；最后一图A面板无框表示无有效响应，绝不表示无水印。

## 文件与Windows运行

最终Job：D:\GitHub\MyE-C-skill\aliexpress-product-image-audit\work\8788-observed-audit-20261114\OBSERVED_20261114T064013Z_1d1fd636b0764847a51c079c8142f8c3
最终详细JSON/叠加图：该Job/observed-audit-report.json、observed-audit-report.md、8788-real-validation-overlay。
请求来源：continuation-scope.json、observed-request-records.json、父Job原始响应及子Job observed-raw；不重复计算父结果。
本轮Token核验：reports/8788-observed-token-verification.json。测试日志：8788-observed-full-tests.log，状态和源码清单同前缀。
最终验证：8788-observed-final-verification.json；新增测试名单：8788-observed-new-tests.json。

```powershell
Set-Location 'D:\GitHub\MyE-C-skill\aliexpress-product-image-audit'
$py = '..\ae-img-audit\.venv\Scripts\python.exe'
$env:PYTHONPATH = (Resolve-Path .\scripts).Path
& $py .\scripts\complete_observed_audit.py --help
& $py .\work\8788-observed-audit-preparation\run_offline_tests.py
& $py .\scripts\complete_observed_audit.py
```

以上默认只准备离线Job，不调用模型。需要启动下一次固定六图审核时，另行明确启动观察模式，并在进程环境提供既有VLM_API_KEY；不要重复执行本轮的父Job。
真实入口参数为--execute-observed-models --user-statement；会产生新调用，不代表自动获得下一次运行授权。本轮已停止模型调用。

## 未验证与回滚

未验证真实账单、远端原厂模型版本、线上SKU当前状态、新商品批量泛化或自动整改；缺字段响应本轮仍是异常，型号和颜色UNKNOWN未解决。
没有线上写入，无需线上回滚。要撤回本轮入口可移走两个新增脚本和测试，按基线补丁还原可选HTTP参数；保留所有Job、原始证据、源码快照与报告。
