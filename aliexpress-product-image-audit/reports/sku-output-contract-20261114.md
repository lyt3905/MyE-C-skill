# SKU 输出契约补缺与真实结果离线复核

## 复现与原因

真实 Job JOB_17ac0d46e3a44f339d2a9a2c34098ebd 共28次调用，27次通过格式校验，SKU_ROW_001 的 DeepSeek 响应遗漏 sku_id 和 image_id，严格校验返回 sku references。输入 safe_payload 已包含两个字段，因此不是程序漏传。

实际请求先使用要求返回引用字段的 SKU 任务提示，随后追加一条只列 task_type/item_id/decision/confidence/abstain/evidence_ids 的通用输出清单。这份较短清单缺少引用字段以及包装字段，存在提示歧义；不能断言它是模型漏字段的唯一原因。新增 Fake 请求测试先复现这份不完整清单，再完成修复。

## 修改

- SKU 请求不再追加那份通用短清单，改由 SKU 任务提示明确列出全部12个输出字段。
- sku_id 和 image_id 即使 abstain=true 也必须原样回传；它们是请求绑定标签，不是商品数据库ID或模型观察。
- 没有放宽 Schema、回填缺失ID、修改置信度或包装判断。缺失/错配引用依旧拒绝。
- SKU Prompt 变化会进入现有缓存指纹，避免复用旧提示结果。水印和身份 Prompt、Schema、聚合器保持不变。

## 测试与回放

新增3项测试覆盖实际发送提示与输入标签、缺失/错配引用拒绝、提示变化隔离缓存；67项针对性 Fake/Mock 测试通过。完整回归 **668 项全部通过**，0 失败、0 错误，耗时 853.5 秒；源码在运行期间未变，网络拦截触发0次。结束后源码与最终测试清单逐文件一致，原真实Job全树及历史433文件封印均核对未变。独立只读复核未发现实质问题。完整回归结果独立保存在 sku-output-contract-full-tests-status.json、sku-output-contract-full-tests.log、sku-output-contract-full-source-manifest.json。

对原始28份真实响应进行离线回放：27份通过，原SKU响应仍因缺少引用字段被拒绝。没有改写真实历史结果，没有将本地提示修复冒充为模型已验证修复。回放记录在 work/sku-output-contract-20261114/offline-replay.json。

水印6份结果本身均通过v3结构校验；UNKNOWN主要来自置信度不足、归属不清、区域未匹配等语义证据原因。此次不以放宽聚合器来制造PASS。

## 证据与源码

原真实Job全树封印在 work/sku-output-contract-20261114/real-evidence-before.json；本轮结束后再次验证。历史433证据文件仍保留。原665项测试对应真实调用源码；此次SKU提示补丁属于后续本地版本，不回写真实验收的来源清单。

新版验收器的逐文件SHA检查函数保持不变，BASELINE指向本轮67项针对性测试生成的独立源码清单。旧665项/真实源码清单及此前各轮清单均未覆盖。

本轮无新模型调用、无新审核Token、无线上写入。真实40次授权已使用28次，剩余额度未在本轮使用。本轮改动未执行新的模型验收，因此不能保证模型今后不再漏字段。

## 交付与回滚

本轮专用差异：work/sku-output-contract-20261114/task-only.diff；对应原文件在同目录baseline。只回滚本轮差异，不对共享仓库整体reset，不删除原真实Job、响应或历史证据。未提交或推送GitHub。

Windows离线复核：

```powershell
Set-Location 'D:\GitHub\MyE-C-skill\aliexpress-product-image-audit'
$py = '..\ae-img-audit\.venv\Scripts\python.exe'
$env:PYTHONPATH = (Resolve-Path .\scripts).Path
& $py -m unittest discover -s tests -p test_sku_output_contract.py -v
```
