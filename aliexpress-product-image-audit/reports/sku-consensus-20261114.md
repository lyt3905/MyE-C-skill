# SKU 字段补缺真实验证与状态一致性修复

## 真实只读补充验证

在用户原40次模型请求授权范围内新增2次，仅复查 Shop7/PID5097/SKU_ROW_001；累计30次，未重跑整件商品。新建独立SKU_CANARY任务，旧Job没有启动或覆盖。原商品、店铺和账号在请求前后校验一致；上传、保存、翻译、整改均为0。

使用668项测试对应版本，两路模型均回传了必需的sku_id/image_id，2份响应都通过严格校验。该提示补丁获得一次真实通过的例子，不能保证后续永不漏字段。

本次2次网关报告6178 Token（输入5146＋输出1032）：DeepSeek3021、Kimi3157。与原28次合计30次、177351 Token（输入104804＋输出72547），供应商真实账单仍未核实。剩余10次授权额度未使用。

## 验证暴露的问题

DeepSeek返回 image_type=mixed、confidence=0.95；Kimi返回 image_type=box、confidence=0.90；两者均返回MATCH、sku_packaging=with_box。完整商品审核的_sku保守返回UNKNOWN，但客户端只比较MATCH/MISMATCH标签，返回CLEAN。此状态不一致会误导只看客户端状态的调用方。

本轮先以Fake响应复现上述场景，再修复：SKU的image_type、sku_packaging、shared_across_skus、missing_image存在分歧或缺失/unknown时，客户端保留原始观察并返回REVIEW，不能仅因MATCH标签一致就返回CLEAN。完整一致的结果仍可CLEAN；阈值与完整商品业务规则未降低。

同时为SKU提示明确box/product_only/mixed定义，与现有商品身份提示一致：盒窗内可见的玩具和多个盒装单元属于box；未装盒实物与独立包装并列才是mixed。不在已收到的响应中重写图片类型。

## 验证范围

新增4项回归，覆盖真实box/mixed分歧、包装和布尔值分歧、缺失/unknown字段、完整一致结果；71项针对性Fake测试通过。完整回归 **672项全部通过**，0失败、0错误，耗时710.078秒；测试期间源码未变化。结束后当前源码与测试清单逐文件匹配，原完整真实Job、补充验证及历史433文件封印未变。独立只读复核未发现实质问题。完整回归记录在sku-consensus-full-tests-status.json、sku-consensus-full-tests.log、sku-consensus-full-source-manifest.json。

原始两份响应离线回放：旧客户端CLEAN，新客户端REVIEW；观察完全一致，完整业务判断仍UNKNOWN。没有改写真正模型观察，原新旧真实Job均保留。这次回放是Fake运输，不能加入真实调用数或真实Token。

状态一致性与图片类型说明补丁在2次真实验证之后开发；尚未用新增模型请求验证当前最新补丁。不能把668版本的真实验证当成最新版本已获真实验收。

## 交付与保护

真实补充验证目录：`D:\GitHub\MyE-C-skill\aliexpress-product-image-audit\work\authorized-mainflow-5097-20261114T094454Z\SKU_CANARY_20261114T102742Z_5435de6e`；原始响应见metrics.json的raw_response，实际2次请求、0重试、0缓存命中。executed-source.zip和authorization.json绑定668版本源码、测试清单与启动器SHA；不包含密钥。原40次授权通过独占续跑声明预留2次，并以单独持久预算将本次限制在2次，总计不超过30；保留原Token和图片预算余量，未重置旧账本。

离线回放：work/sku-consensus-20261114/offline-replay.json；真实补充验证全树封印：同目录real-canary-before.json。旧665真实Job、668补充验证及历史433证据分别保留，后续源码不回写旧来源清单。

本轮差异：work/sku-consensus-20261114/task-only.diff；原文件在同目录baseline。只回滚对应差异，不对共享仓库整体reset。未提交或推送GitHub。

## 当前结论

SKU请求字段可完整返回的真实路径已验证，客户端状态分歧也已通过离线回放纠正；整件商品的水印、身份、模板不确定仍未解决。当前不能宣称整件商品自动审核已全部通过，也未执行自动整改。后续优先核查模型图像输入是否保留原始细节，继续维持SOP与未知结论保护。
