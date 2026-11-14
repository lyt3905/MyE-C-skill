# Shop 7 / 5097：8788 只读续跑结果

源码证据更正：[原清单与GitHub仓库字节的逐文件核对](full-product-audit-8788-source-reconciliation.md)。原清单为Windows本地原始字节SHA256，不能直接与Git归一化后的文件哈希等同；原清单保持不变，差异与证明范围另行列明。

审核未完成（INCOMPLETE）；已知不合规（NON_COMPLIANT）；本轮整改未执行。
2026-11-14，用户明确授权新增最多28次请求、500,000 Token后，切回8788接口完成本次只读续跑。
主图6张、详情图6张、SKU图池2张、SKU引用2处，共16个业务位置、6份不同图片内容，全部保留逐项记录。
14个语义审核任务现均有两份模型结果；“模型有返回”不代表“结论满足门槛”。
本轮28次请求、实报158,091 Token，用量全部已知。原阶段22次请求的已知小计115,716 Token，仍有1次未知；两个阶段合计50次请求、已知小计273,807 Token，总量仍UNKNOWN。
原任务、旧预算及原始证据哈希均未改变。新增额度已用满并关闭本地续跑授权。

## 逐位置覆盖矩阵

| 位置（从0开始） | 字节/尺寸 | 水印归属 | 型号/颜色/画面类型 | SKU包装匹配 | 总结论 |
|---|---|---|---|---|---|
| MAIN_000 | PASS/PASS | UNKNOWN | PASS | 不适用 | UNKNOWN |
| MAIN_001 | PASS/PASS | UNKNOWN | PASS | 不适用 | UNKNOWN |
| MAIN_002 | PASS/PASS | UNKNOWN | UNKNOWN | 不适用 | UNKNOWN |
| MAIN_003 | PASS/PASS | UNKNOWN | UNKNOWN | 不适用 | UNKNOWN |
| MAIN_004 | PASS/PASS | UNKNOWN | UNKNOWN | 不适用 | UNKNOWN |
| MAIN_005 | PASS/PASS | UNKNOWN | UNKNOWN | 不适用 | UNKNOWN |
| DETAIL_000 | PASS/PASS | UNKNOWN | PASS | 不适用 | UNKNOWN |
| DETAIL_001 | PASS/PASS | UNKNOWN | PASS | 不适用 | UNKNOWN |
| DETAIL_002 | PASS/PASS | UNKNOWN | UNKNOWN | 不适用 | UNKNOWN |
| DETAIL_003 | PASS/PASS | UNKNOWN | UNKNOWN | 不适用 | UNKNOWN |
| DETAIL_004 | PASS/PASS | UNKNOWN | UNKNOWN | 不适用 | UNKNOWN |
| DETAIL_005 | PASS/PASS | UNKNOWN | UNKNOWN | 不适用 | UNKNOWN |
| SKU_000 | PASS/PASS | UNKNOWN | UNKNOWN | 不适用 | UNKNOWN |
| SKU_001 | PASS/PASS | UNKNOWN | UNKNOWN | 不适用 | UNKNOWN |
| SKU_ROW_000 | PASS/PASS | UNKNOWN | UNKNOWN | PASS | UNKNOWN |
| SKU_ROW_001 | PASS/PASS | UNKNOWN | UNKNOWN | PASS | UNKNOWN |

两条SKU包装匹配最终均PASS，但其引用图片的完整身份/水印检查仍有UNKNOWN，不能把SKU包装通过当作整件合规。

## 逐图分歧与证据

| 不同内容 | 业务位置 | 水印模型结果（分类/置信度） | 身份模型结果（类型/置信度） |
|---|---|---|---|
| 20583cfb87a9ac7e | MAIN_000, DETAIL_000 | third_party_store_banner/0.98；third_party_store_banner/0.93 | BOX/0.93；BOX/0.95 |
| f58ef0242d0737a4 | MAIN_001, DETAIL_001 | unknown/0.45/弃权；social_account_signature/0.78 | FIGURE/0.93；FIGURE/0.9 |
| e9a1233b0d4e4282 | MAIN_002, DETAIL_002 | unknown/0.35/弃权；unknown/0.42/弃权 | FIGURE/0.93；FIGURE/0.86 |
| 4292661510e41155 | MAIN_003, DETAIL_003, SKU_001, SKU_ROW_000 | photographer_credit/0.92；photographer_credit/0.82 | FIGURE/0.92；FIGURE/0.88 |
| b001256f37783043 | MAIN_004, DETAIL_004 | photographer_credit/0.84；photographer_credit/0.9 | FIGURE/0.92；FIGURE/0.84 |
| 0fd90100f20a2edc | MAIN_005, DETAIL_005, SKU_000, SKU_ROW_001 | manufacturer_branding/0.9；product_print/0.9 | MIXED/0.95；BOX/0.85 |

已确认：MAIN_000 / DETAIL_000 的店铺横幅，模型根结论置信度0.98/0.93。图中仍有其他小字归属未确定，因此完整水印检查保持UNKNOWN，但已知问题单列保留。
其余不确定包括摄影署名/原厂小字归属、0.82～0.88等低于0.90的结论，以及盒图BOX/MIXED冲突；均没有改写置信度或移除规则。
精确哈希匹配的4份既有人工作答作为来源证据提供给模型，未冒充新模型结论、未用于覆盖弃权。

## 商品级检查

| 规则 | 结果 |
|---|---|
| ocr_available | PASS |
| near_duplicate_review | PASS |
| template_configuration | PASS |
| gaussian_highpass_coverage | PASS |
| brand_mapping | PASS |
| source_state_and_account_unchanged | PASS |
| required_pool_main | PASS |
| required_pool_detail | PASS |
| required_pool_sku | PASS |
| main_count_1_to_6 | PASS |
| main_exact_duplicates | PASS |
| sku_pool_reference_0 | PASS |
| sku_pool_reference_1 | PASS |

## 整改建议与限制

确认的店铺横幅需要整改，优先取得同款干净原厂素材或验证仅去除背景覆盖层的方案。该图包含原厂盒图，不直接执行整图删除。
摄影署名、原厂印刷、版权与包装内容继续保护。其余UNKNOWN项目保持原样，不能按未知直接删除。
本轮没有生成可直接执行的写入计划；未上传、保存、删除、翻译或改变商品状态。Description与其采集内容/图片完全排除，价格、利润率、运费和派生售价排除，标题未做模型复核。

## 测试与源码

最终完整回归534项通过，261.861秒，退出码0：full-audit-recovery-full-tests.log。包含新增7项Fake恢复测试：未授权拒绝、账号/商品/远端图片变化阻止、只补未确定项目、原预算不变、UNKNOWN总量保留及重复启动拒绝。
新增源码：scripts/full_audit_recovery.py；测试：tests/test_full_audit_recovery.py。复用既有预算、模型、下载和逐项校验代码。
一次格式错误在剩余额度内补试；BOX/MIXED定义分歧只重试一个模型并保留另一独立模型结果，所有历次结果与请求账本均保留。

## Windows查看与验收

```powershell
Set-Location 'D:\GitHub\MyE-C-skill\aliexpress-product-image-audit'
$env:PYTHONPATH = 'scripts'
& '..\ae-img-audit\.venv\Scripts\python.exe' -m unittest discover -s tests -v
& '..\ae-img-audit\.venv\Scripts\python.exe' scripts/full_audit_recovery.py --help
```

本次授权已消耗并关闭，不要重复启动。本机接口为http://127.0.0.1:8788/v1，模型deepseek-v4.1-flash与kimi-k3-1；密钥没有写入源码或报告。

## 回滚及未验证项目

本轮商品写入为0，无需线上回滚。保留原任务与recovery_8788_1证据；撤回开发改动时仅撤回新增恢复入口及相关测试，不覆盖之前已交付的SKU修复。
仍未证明：一件真实商品全部自动审核达标、所有细小/浅色标记归属、所有角度型号身份、任意商品批量审核，以及新增真实整改。没有把这些未证明项标记完成。
下一步需要有针对性的更强视觉/来源证据；当前授权已用满，不再自动重复请求来追求更高置信度。

原始最终报告：D:\GitHub\MyE-C-skill\aliexpress-product-image-audit\work\full-product-audit-20261114\jobs\JOB_93099438cf014a689846bc05469759ad\recovery_8788_1\final_report.after-component.json
完整覆盖矩阵：full-product-audit-8788-coverage.json；本次汇总：full-product-audit-8788-result.json。
