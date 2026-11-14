# Shop 7／5097 新版正式入口真实只读验收（2026-11-14）

执行链已完成，商品审核结论仍不完整。不能将本报告解读为商品合规或已达到完全无人复核的审核质量。

## 执行结果

- 使用用户明确授权的新建独立 Job：`JOB_17ac0d46e3a44f339d2a9a2c34098ebd`；未重启任何旧 Job，未运行 full_audit_recovery.py。
- 正式入口 `workflow_runner.py full-audit`，28／28 次计划请求完成，重试 0；低于授权上限 40，余下额度未使用。
- 6 份不同图片内容，16 个业务位置（6 主图＋6 详情图＋2 SKU 图＋2 SKU 引用），全部在覆盖矩阵中报告。
- 27 次响应通过校验，1 次 SKU 响应异常被保留，未中断其余审核。没有为了凑齐结论重试或补造字段。
- 源商品状态与账号复核未变；上传、保存、翻译、状态修改及自动整改均为 0。
- 正式入口运行耗时 187.39 秒（含采集、下载、OCR、模型与报告）。

## 模型与用量

| 模型 | 请求 | 校验通过 | 异常 | 网关报告 Token |
|---|---:|---:|---:|---:|
| deepseek-v4.1-flash | 14 | 13 | 1 | 99755 |
| kimi-k3-1 | 14 | 14 | 0 | 71418 |

合计：171173 Token（输入 99658，输出 71515）。全部请求都有可读取用量；以上是网关报告，供应商真实计费尚未核实，也不证明图片 Token 存在可靠硬上界。

## 业务结论与未完成项

- `audit_status=INCOMPLETE`；`compliance_status=UNDETERMINED`；`audit_complete=false`。
- 6 份图片的水印结论均 UNKNOWN：存在低置信度、归属不明、小字不可读、区域匹配不足等；不能认定全部干净，也不能认定全部存在店铺水印。没有调低阈值或把包装文字直接认定为水印。
- 6 份图片的身份综合结论均 UNKNOWN：主要是型号不可见、低置信度、证据不足和部分颜色/主体分歧。该结论没有阻断整批执行。
- 无盒 SKU 包装检查 PASS；有盒 SKU 包装检查 UNKNOWN。DeepSeek 在 SKU_ROW_001 中遗漏必需的 sku_id、image_id，校验报 sku references；原始响应完整保留，未用请求字段回填为模型证据。
- 唯一未确定的全局检查为模板配置；Shop 7 保持 REQUIRED_TEMPLATE_MISSING。
- 报告中未确定计数 17 是 16 个业务位置＋1 项全局检查，包含重复图片位置，不是 17 张不同图片或 17 个独立程序故障。
- Description、价格及标题复核未进入模型审核；原始商品快照为留证而保留其原值。

## 证据与源码绑定

- 源码与 665 项测试所绑定的 266 个文件逐一匹配；运行前后均核对，源码未修改。
- 本次运行源码归档：`D:\GitHub\MyE-C-skill\aliexpress-product-image-audit\work\authorized-mainflow-5097-20261114T094454Z\executed-tested-source.zip`。
- 归档、清单与启动器 SHA256 见 `D:\GitHub\MyE-C-skill\aliexpress-product-image-audit\work\authorized-mainflow-5097-20261114T094454Z\source-provenance.json`；不包含模型密钥或站点凭据。
- 模型密钥仅从用户指定文件在验收进程内读取，进程结束时清除，未复制内容到报告、配置、源码或命令。
- 原始模型响应见 Job 的 full_ai_metrics.json 中每次调用的 raw_response；规范化结果见 full_ai_judgements.json。
- 原始采集、图像、OCR、视图、模板状态、用量和报告均保留；Job 证据清单中 365 个文件 SHA256 复核一致。
- 历史 433 个证据文件封印再次通过，旧审核文件未覆盖。

## 交付位置

- Job：`D:\GitHub\MyE-C-skill\aliexpress-product-image-audit\work\authorized-mainflow-5097-20261114T094454Z\jobs\JOB_17ac0d46e3a44f339d2a9a2c34098ebd`
- 结构化汇总：`D:\GitHub\MyE-C-skill\aliexpress-product-image-audit\work\authorized-mainflow-5097-20261114T094454Z\acceptance-summary.json`
- 完整业务报告：`D:\GitHub\MyE-C-skill\aliexpress-product-image-audit\work\authorized-mainflow-5097-20261114T094454Z\jobs\JOB_17ac0d46e3a44f339d2a9a2c34098ebd\full_audit_report.json`
- 覆盖矩阵：`D:\GitHub\MyE-C-skill\aliexpress-product-image-audit\work\authorized-mainflow-5097-20261114T094454Z\jobs\JOB_17ac0d46e3a44f339d2a9a2c34098ebd\coverage_matrix.json`
- 模型原始响应及用量：`D:\GitHub\MyE-C-skill\aliexpress-product-image-audit\work\authorized-mainflow-5097-20261114T094454Z\jobs\JOB_17ac0d46e3a44f339d2a9a2c34098ebd\full_ai_metrics.json`

## 后续建议

优先处理 SKU 响应字段完整性与水印判定可用性，再考虑身份细分优化；模板缺失继续明确保留。后续修改应先用本次原始响应离线回放和 Fake 测试，不修改本次证据或降低审核标准。本轮未追加模型请求，也未执行自动整改。
