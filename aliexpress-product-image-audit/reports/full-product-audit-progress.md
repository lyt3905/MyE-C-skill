# Shop 7 / PID 5097 全量自动审核进度

目标尚未完成。审核结论：INCOMPLETE；合规状态：NON_COMPLIANT。
本报告仅对已保存的真实证据做字段格式兼容处理，没有新增网站或模型调用，没有修改原始 Job 报告或预算。
14 个图片位置、2 个 SKU 引用，6 份不同图片内容；所有位置保留，未按业务位置重复请求模型。
双模型及 0.90 阈值未降低，所有低置信、归属不清和缺失结果保留 UNKNOWN。

| 位置 | 水印归属 | 型号/颜色/包装 | SKU 引用 | 总结论 |
|---|---|---|---|---|
| MAIN_000 | UNKNOWN | PASS | 不适用 | UNKNOWN |
| MAIN_001 | UNKNOWN | UNKNOWN | 不适用 | UNKNOWN |
| MAIN_002 | UNKNOWN | UNKNOWN | 不适用 | UNKNOWN |
| MAIN_003 | UNKNOWN | UNKNOWN | 不适用 | UNKNOWN |
| MAIN_004 | UNKNOWN | UNKNOWN | 不适用 | UNKNOWN |
| MAIN_005 | UNKNOWN | UNKNOWN | 不适用 | UNKNOWN |
| DETAIL_000 | UNKNOWN | PASS | 不适用 | UNKNOWN |
| DETAIL_001 | UNKNOWN | UNKNOWN | 不适用 | UNKNOWN |
| DETAIL_002 | UNKNOWN | UNKNOWN | 不适用 | UNKNOWN |
| DETAIL_003 | UNKNOWN | UNKNOWN | 不适用 | UNKNOWN |
| DETAIL_004 | UNKNOWN | UNKNOWN | 不适用 | UNKNOWN |
| DETAIL_005 | UNKNOWN | UNKNOWN | 不适用 | UNKNOWN |
| SKU_000 | UNKNOWN | UNKNOWN | 不适用 | UNKNOWN |
| SKU_001 | UNKNOWN | UNKNOWN | 不适用 | UNKNOWN |
| SKU_ROW_000 | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| SKU_ROW_001 | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |

## 未完成原因

1. 22 次实际请求中 1 次网关 502 且缺失用量；预算保护已停止后续请求，两个 SKU 判断和一项第二模型判断缺失。
2. 部分图片的摄影署名、浅色文字或印刷归属低于 0.90；型号、颜色或包装观察仍有低置信或不完整结论。
3. 已确认存在店铺横幅的图片仍有其他未明确归属的文字，不以发现一个问题代替该图所有审核项目完成。
4. 网关页面显示该次失败内部有 2 次尝试；程序记录 22 次 HTTP 调用，不能把它称作 22 次上游推理。

## 执行和范围

本目标上传、保存、翻译、删除和状态修改均为 0。Description、采集正文和正文图片均排除；价格、利润率、运费及派生售价排除；不对标题做模型复核。
本次字段兼容仅把 observed_model、observed_color 复制到规范字段；保留原值和置信度，没有推定或提升结论。
原始真实记录：D:\GitHub\MyE-C-skill\aliexpress-product-image-audit\work\full-product-audit-20261114\jobs\JOB_93099438cf014a689846bc05469759ad。

## 下一步与整改限制

先取得失败请求的可信用量记录并完成预算对账，再从已有证据继续；不得清空预算或创建新 Job 绕过 UNKNOWN。
归属不清的印刷和摄影署名保持原样。确认店铺覆盖层后，优先匹配同款干净原厂图；整图删除需另证实不会删除包装、原厂内容或唯一信息。
本报告没有可直接执行的线上整改授权。先完成所有应审结论，之后才能讨论新增真实整改。

## Windows 验收命令

```powershell
Set-Location 'D:\GitHub\MyE-C-skill\aliexpress-product-image-audit'
$env:PYTHONPATH = 'scripts'
& '..\ae-img-audit\.venv\Scripts\python.exe' -m unittest discover -s tests -v
```

当前不建议重新执行 full-audit：真实 Job 已因 UNKNOWN 用量停止。检查只读命令参数可运行：
```powershell
& '..\ae-img-audit\.venv\Scripts\python.exe' scripts/workflow_runner.py full-audit --help
```

## 回退

本轮未写商品，无需线上回滚。若需撤销新增全量审核入口，应保留当前证据和预算，并仅撤回本轮 full_product_audit、新 CLI 入口及兼容字段改动，不覆盖之前 SKU 修复和其他未提交源码。

## 已确认问题与未确认项目分别记录

审核仍为 INCOMPLETE；已知存在不合规内容，因此合规状态为 NON_COMPLIANT。这不代表整件审核已完成，也不构成删除或整改授权。

| 位置 | 已确认问题 | 后续限制 |
|---|---|---|
| MAIN_000 | 双模型均确认店铺横幅 | 其他文字归属未全部确定；原厂印刷保护，不整图删除 |
| DETAIL_000 | 双模型均确认店铺横幅 | 其他文字归属未全部确定；原厂印刷保护，不整图删除 |

实际调用 22 次；21 次有实际用量，已知小计 115,716 Token，1 次用量 UNKNOWN，另有 3 条调用在发送前被阻止。总 Token 仍 UNKNOWN。

## 测试记录

- 完整回归：524 项通过，363.134 秒，退出码 0；日志 full-product-audit-final-tests.log。该运行在最终报告区分修复前启动，不能冒称最终所有源码在一次全量运行中验证。
- 最终局部修复：先复现已确认水印被 UNKNOWN 掩盖的失败；修复后 19 项全量审核专项通过，0.841 秒。日志 full-product-audit-confirmed-findings-red.log / full-product-audit-confirmed-findings-green.log。专项与全量有重叠，不将两者数量相加。
- CLI 参数入口检查通过；Fake/Mock 验证全量图片位置覆盖、只读执行和无 Writer。
- 真实全量审核没有完成；测试通过不等于真实商品结论齐全。用量 UNKNOWN 仍未恢复，不重试、不重置预算。

## 网关用量与并发记账核查

已匹配本地用量记录：2026-11-14 02:35:28，HTTP 502，90,017 毫秒，2 次内部尝试；请求编号 `364ee2d99f3561de418ff4d5d743ae4c`。请求存档目录不存在。输入/输出零字段没有供应商用量凭证，不据此解锁预算。

只读检查原预算数据库：known=0，数据库已记已知小计98,398，而逐次真实返回的小计为115,716，差额17,318。根因是某请求用量未知后，其他在途成功响应也被错误按未知结算。Fake 并发测试先复现0而不是50的漏记，再修复为逐次响应独立结算，UNKNOWN锁定仍保持；相关49项测试通过（3.018秒）。没有修改历史真实预算或原始Job。

继续条件：取得失败请求（含两次内部尝试）的可信实际用量，再对账逐次已知差额和未知消耗，随后在原任务补齐缺失判断与剩余不确定项。不得靠新建任务、换样本、重复请求或清空预算绕过。详细证据见 full-product-audit-blocker-evidence.json。

## 最新：已授权8788续跑完成

详见 full-product-audit-8788-result.md。新增28次请求、158091实报Token，均已知；累计未知仍保留。14任务均有双模型结果，SKU包装匹配两项PASS，但16位置仍有语义UNKNOWN，整件未完成。最终534项完整回归通过；写入0。

## 原厂来源补查

检索到DW-ES09T与Toxitron配色对应的两篇第三方资讯，均归因于原厂社交渠道；正文访问403，候选原厂微博不可访问，尚未验证原帖及原始图片。仅保留为来源线索，不作为原厂真实性或具体图片归属的真值，也不提高模型置信度。无新增模型调用或商品写入。来源与访问状态：full-product-audit-manufacturer-source-investigation.json。
