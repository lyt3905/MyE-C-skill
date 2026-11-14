# 8788真实模型小批量验收：最终预检报告

**PREFLIGHT_BLOCKED：本轮仅本地准备，未启动真实模型。**

源码/输入/隔离检查通过，预检Runner与Fake预算回归完成；提供方单请求总Token硬上界尚未核实，真实适配器未启用。不能宣称已具备可运行的真实验收能力。

## 工作区与来源

- 仓库：D:/GitHub/MyE-C-skill；项目aliexpress-product-image-audit。
- 分支codex/8788-contract-local-fix-20261114；HEAD 8399a4eb2c213c43cbebd0350de601556d9eb052。
- 沿用本地修复，不切换main、不覆盖源码；其他项目已有改动不触碰。完整status见新Job/preparation.json。
- 上一轮253个源码/测试/配置文件逐字节匹配；没有沿用567项数字冒充本轮新代码验证。
- watermark/v3、product-identity/v3；Prompt与Schema/Cache/聚合器源码哈希已封存；IoU=0.5、双模型和0.90不变。缓存禁用，不复用历史模型结果。
- 当前配置来自work/operational-20261113-7adadd47/model.json：127.0.0.1:8788/v1，deepseek-v4.1-flash、kimi-k3-1，max_output_tokens8192，retries0，timeout150。
- 仅核对本地配置ID；无网络探测，不声称已验证提供方实际解析的模型版本。

## 六图输入

| 完整SHA256 | 宽高 | 业务位置 |
|---|---|---|
| 20583cfb87a9ac7e0ccf022650a3b262f88d4c9b33eea83e990982d2f8c13b82 | [800, 800] | MAIN_000, DETAIL_000 |
| f58ef0242d0737a4aa4d8c4997e72842049679a391df89c3c6d9179f4264bed6 | [800, 800] | MAIN_001, DETAIL_001 |
| e9a1233b0d4e4282e657d83b75d9f3cdf2636b30dd5591733ded7201b65e0bc7 | [800, 800] | MAIN_002, DETAIL_002 |
| 4292661510e41155463451b49d871611c08827bdb1b6dd0701a484eb4c05e8b7 | [800, 800] | MAIN_003, DETAIL_003, SKU_001, SKU_ROW_000 |
| b001256f377830437d16b2f0b151cc6114d85ea7cdde5e697adf1d9f1c37b82e | [800, 800] | MAIN_004, DETAIL_004 |
| 0fd90100f20a2edcdd286946646bce31346160d172810ddb5fe6a39ef87cc7a5 | [800, 800] | MAIN_005, DETAIL_005, SKU_000, SKU_ROW_001 |

每个原始文件路径、字节数、图片格式、OCR数量、辅助图路径/SHA/尺寸/证据ID均见8788-real-validation-inputs.json。
所有输入只从封存图像inventory/queue提取；未解析audit_product.json或描述字段，未OCR新内容、未抓取线上商品。
完整SHA作为内容匹配键；12个图像任务对应24次请求；SKU图池及两行引用仅复用图像结果，无额外4次SKU请求。
旧Job含SKU快照的433个文件均哈希不变；未访问网站，不声称当前线上SKU未发生变化。

## 独立Job与预算状态

D:\GitHub\MyE-C-skill\aliexpress-product-image-audit\work\8788-real-validation-20261114\VALIDATION_20261114T045053Z_66cedcb39b524be9be8cc93c51e7898f

新Job独立保存inputs、source-versions、model-profile、request-plan、preparation、historical-comparison及任务书要求的全部预检输出。
请求账本为空，预算已用0，无授权；raw/normalized目录为空，overlay仅NOT_RUN索引，不伪造真实区域。
另有独立、明确标注FAKE的24次模拟任务留档，不能代替真实结果。

| 检查项 | 结果 |
|---|---|
| 本地源码及上一轮测试哈希 | PASS |
| 六图完整SHA/可读取/800x800/证据绑定/16位置 | PASS |
| 新Job隔离、433旧文件不变 | PASS |
| 默认预检、互斥模式、无site/writer/cache/recovery入口 | PASS |
| 24次请求预算、失败计数、串行零重试（Fake） | PASS |
| 300000累计上限、逐次预留、未知用量/超时/格式/模型变更即停（Fake） | PASS |
| 真实提供方单请求总Token上界 | BLOCKED：缺少可验证保证 |
| 提供方实际模型解析版本 | NOT_VERIFIED：未访问网关 |
| 真实结构/区域定位/语义质量验收 | NOT_RUN |

8192仅是输出Token限制，不能证明一次调用的输入+输出不会超出剩余额度。HardBudget.reserve(None)会在计数/发送前拒绝；真实模式目前始终阻断，没有绕过参数。
必须先验证提供方输入预计数上界或服务端总Token限额，再接入逐请求上界并补测/重新预检；仅新增用户授权不能替代这个保证。本轮未编造上界、未复用旧28次额度、未扩大到500000。

## 测试和独立本地复核

完整回归：587项，0失败、0错误，耗时298.016秒（含准备）。新增20项方法。运行ID：29ad8bc7497d4bb8a4218ab5687638be。
测试主进程禁止URL/TCP网络；子进程沿用Fake执行器、本地SQLite/Windows命名管道。捕获外网尝试0；真实模型请求/新增审核Token/线上写入/自动整改均0。
本轮测试源码前后哈希一致，交付时再次核对；旧报告和旧567项测试清单未覆盖。
红绿记录包括：缺少Runner导入失败；首次15项两处错误；叠加图/失败用量缺项失败；历史目录Fake启动隔离失败（测试拦截写入，旧证据未改）。修复后18项通过，再增加到20项并纳入完整套件。
最后本地代码复核确认真实模式无可达发送路径、原始账本不可重启、Fake不得写入历史目录、未知Token不会置零；未调用额外模型评审。
真实传输辅助函数未联网验收，尚未接入真实执行循环；这属于阻断项，不算真实Runner已上线。

## 交付与验收命令

- 源码：scripts/run_8788_real_validation.py；测试：tests/test_8788_real_validation.py。
- 完整日志：reports/8788-real-validation-full-tests.log；状态和新源码清单：8788-real-validation-tests-status.json / 8788-real-validation-test-source-manifest.json。
- 预检定位：reports/8788-real-validation-preflight-location.json；最终机器结果：8788-real-validation-preflight-final.json。
- Fake模拟留档定位：reports/8788-real-validation-fake-simulation.json；--help输出：8788-real-validation-help.txt。
- 运行离线套件：..\ae-img-audit\.venv\Scripts\python.exe work/8788-real-validation-preparation/run_preparation_tests.py。

```powershell
预检命令（不会调用模型；当前预期exit2/PREFLIGHT_BLOCKED）：
Set-Location 'D:\GitHub\MyE-C-skill\aliexpress-product-image-audit'
$py = '..\ae-img-audit\.venv\Scripts\python.exe'
$env:PYTHONPATH = (Resolve-Path .\scripts).Path
& $py .\scripts\run_8788_real_validation.py `
  --source-job-dir .\work\full-product-audit-20261114\jobs\JOB_93099438cf014a689846bc05469759ad `
  --input-manifest .\reports\8788-real-validation-inputs.json `
  --output-dir .\work\8788-real-validation-20261114 `
  --model-config .\work\operational-20261113-7adadd47\model.json `
  --max-provider-requests 24 `
  --max-total-tokens 300000 `
  --no-retry `
  --no-site-write `
  --preflight-only

真实模式目标命令（本轮未运行，当前仍会被硬预算预检拒绝）：
必须先验证提供方单请求输入/总Token上界并完成适配、Fake测试、PREFLIGHT_PASS；
然后另获用户明确24次请求/最多300000Token授权。单凭授权不能绕过预算阻断。
Set-Location 'D:\GitHub\MyE-C-skill\aliexpress-product-image-audit'
$py = '..\ae-img-audit\.venv\Scripts\python.exe'
$env:PYTHONPATH = (Resolve-Path .\scripts).Path
& $py .\scripts\run_8788_real_validation.py `
  --source-job-dir .\work\full-product-audit-20261114\jobs\JOB_93099438cf014a689846bc05469759ad `
  --input-manifest .\reports\8788-real-validation-inputs.json `
  --output-dir .\work\8788-real-validation-20261114 `
  --model-config .\work\operational-20261113-7adadd47\model.json `
  --max-provider-requests 24 `
  --max-total-tokens 300000 `
  --no-retry `
  --no-site-write `
  --execute-real-models

```

真实命令本轮未执行；当前即使指定--execute-real-models也返回PREFLIGHT_BLOCKED/exit2、请求0。预算适配未完成前不要启动。
本轮到此停止。只有后续预算条件补齐、PREFLIGHT_PASS且另获24次/最多300000Token授权后，才能启动真实验收；之后也不允许整改或线上写入。

## 回滚和未验证项

本轮业务源码仅新增Runner与测试，旧修复代码未改；要撤回本轮功能只需移走这两个新增文件，保留所有证据/Job/报告。无线上变化，无线上回滚。
未验证：实际8788连接/鉴权/模型版本、供应商输入Token上界或总Token限额、真实Schema稳定性、bbox准确性、双模型区域匹配质量、署名/原厂归属、真实置信度校准、人工overlay核验、线上SKU现状。
没有独立可靠标注真值，不能报告识别准确率。没有新真实结果，不能宣布与历史结论一致或审核完成。未提交/推送GitHub。
