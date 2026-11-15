# 保存和独立回读

IMPLEMENTED / FAKE_VERIFIED，真实线上NOT_RUN。

正式CLI任务：D:\GitHub\MyE-C-skill\aliexpress-product-image-audit\work\v2-full-workflow-20261115T170312\retained-cli\bd7e53c93a3e48bc80d50bb9e382e9d7\cli-jobs\JOB_acd9d314ad244efdbab305a11bd5426f，最终PARTIALLY_AUTO_FIXED，1模拟上传/1保存，独立回读通过。该任务明确为Fake，不是Shop7线上PID1的写入。22场景详情v2-full-workflow-fake-evidence.json；CLI证据v2-full-workflow-cli-evidence.json；本地推理v2-full-workflow-local-runtime.json。

回读不只比较URL：原图引用按full_inventory SHA，上传引用按upload_receipts SHA，遍历主图/详情/SKU池和每条真实SKU图片引用。删除、数量、顺序和SKU地址还须与expected_after一致。independent_after.json保存重新读取快照；content_validation.json记录其SHA及每张图的expected/observed SHA。

非图片字段按完整快照去除允许变更的图片字段后精确序列化比较，SKU除图片引用外的属性全部比较；Description存在性、原值及原类型单独比较，且不进入Prompt/下载/语义审核。

已证实Fake故障：相同URL内容漂移、保留图/候选图字节变化、Description变化、SKU引用变化均不能宣称通过。保存超时不重发；已生效但响应丢失时recover-readback+verify-saved只读恢复，有证据确认后更新状态。
