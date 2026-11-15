# shana1 / PID5097 正常主流程真实结果

2026-11-14；Shop7（后台店铺列表核实为shana1）；商品：https://39.107.244.239/products/5097 。

用户本轮授权全部图片整改动作，不外部找图；Token仅记录，不以前置预算/价格核验阻断。最终状态 **PARTIALLY_AUTO_FIXED**。

## 已实际完成

- 主图第1张 main[0]、详情图第1张 detail[0]：移除顶部已由双模型确认的 Mr. Li's Studio Store 店铺横幅。
- 复用原始图片，仅裁去顶部43像素，按原模块等比例白底补方输出800×800；商品盒、厂牌印刷、型号和其余图文保留。
- 两个业务位置使用同一候选，SHA去重上传1次、商品保存1次；翻译/状态推进/删除/擦除/外部找图均0。
- 整改候选双模型质量复核通过。独立线上GET与下载证实两处都为批准候选的相同字节。
- 实际SHA：`db565e3d312986567a52b4d4deba87a89147f832d55deb751b2e99d90da05949`；候选与线上均800×800。
- 状态、价格、重量、标题及翻译、identityJson、品牌、Description、SKU记录均原值原类型不变；其余图片及顺序不变。

## 未完成项

保留20条暂缓记录（不是20张图片），含重复业务位置的归属/身份/型号可见性/SKU待确认，以及未授权的标题异常。该状态不表示整件商品已经全图合规。

## 运行及修复证据

1. `JOB_044c6505107a4776a88885f757b6a39a`：新建真实完整审核，28次模型请求，初版主流程DEFERRED，无上传/保存。
2. `JOB_83e8418a287d4c83b9d58a3a0ba3a595`：复用本轮当前商品未变且Prompt/Schema匹配的已验证语义缓存，修复已确认finding接线与800px裁边；原全图质量复核口径仍挡住局部候选，无上传/保存。
3. `JOB_3297aed9fd4640428c4d4ab86c4191a0`：修正局部动作的质量复核范围，候选通过并完成唯一1上传1保存。写后模型把保留的DW-ES09T型号文字误认作原店铺横幅，曾报告CONTENT_REVIEW_REQUIRED。
4. 保留上述原始响应/失败记录，修复写后衔接：对已经独立质量通过且计划绑定的候选，以重新GET+下载SHA256逐字节相等确认内容；未再次上传或保存。现有任务只读复核及独立复验均通过，状态更新为PARTIALLY_AUTO_FIXED。

执行源码与写后修复源码分别归档在本轮live3/executed-source.zip、executed-source.json、verification-source.json；不会把后续源码改动冒充首次执行已使用的版本。

真实用量合计41次请求，网关报告223943 Token；USD未配置，记null。本轮不做Token优化或费用限额拦截。原始用量与缺失标识见 mainflow-record-only-usage.json。

最终独立核验：mainflow-5097-independent-readback.json。Job、完整候选/计划/授权/回执/回读及模型账本保留在 `work/mainflow-record-only-20261114/live3/jobs/JOB_3297aed9fd4640428c4d4ab86c4191a0`。

## 实际图片

整改前：

![整改前](mainflow-5097-before.webp)

整改后（线上回读原始字节）：

![整改后](mainflow-5097-after.png)
