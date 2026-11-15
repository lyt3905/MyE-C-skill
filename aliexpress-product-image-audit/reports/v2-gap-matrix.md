# V2.0 差距与当前证据

## 当前：Q01–Q24已授权真实只读回归

Q01–Q24的24张本地原图真实只读回归已结束：47次请求（仅DeepSeek/MiMo，无重试），最终动作REVIEW 23、KEEP 1；取得有效输出44条、未取得有效输出3条（含请求失败和格式错误）。本批网关已知Token 350370，未知usage 1次，费用null，仅记录。线上访问、上传、保存、删除和本地整改均0。完整目标仍未完成。

最新结果入口v2-qbatch-acceptance.md。805项离线测试源绑定未变；17份报告的以下旧记录均按原日期和源码检查点保留。OpenCV/完整LaMa已配置，普通本地去字不需要外部编辑配置。

## 前轮本地记录（历史原文保留）

最新完整离线回归：795 项通过，失败/错误/跳过均为0；run_id=1b76237b9bee4738a13a44366b72b38b。测试期间源码一致，无网络尝试；本轮真实模型调用及线上写入0。详见 v2-evaluation-full-tests.log、v2-evaluation-tests-status.json 和 v2-evaluation-test-source-manifest.json。783 项记录仅作为上一版源码历史检查点保留。

| 职责 | 当前结果 | 证据 |
|---|---|---|
| 唯一SHA统一五动作 | 本地/Fake已接入 | image_action_decision、V2视觉测试 |
| run/full-audit路由 | 两入口默认V2；legacy显式 | completion CLI及独立审核测试 |
| 修复→SKU→回读 | 使用上传后expected_after地址，原先误报问题已复现修复 | repaired-image-selected测试 |
| 无盒两图 | 两个SHA进入已有SKU图片池；适用性及旧正确引用受保护 | two-no-box及selector测试 |
| 单SKU双引用 | 未证明服务端能力，现有执行器只绑定一个skuImageUrl | final_state/site_write_client源码 |
| 引用专用图片 | 修复上传、授权删除换引用、REVIEW记录均接入 | reference-only系列测试 |
| 删除与包装材料 | 最后一份盒证据暂缓；另有包装材料时允许删装饰图并校验保留SHA | box-composite系列测试 |
| 真实SKU ID缺失 | 不更改其SKU图片引用，其他明确主/详情修复可继续 | missing-sku-id测试 |
| 本地LaMa | 双Tensor/字典合成TorchScript契约已验证；缺完整权重 | local-torchscript测试/依赖清单 |
| 图像编辑 | 已配置文件/模型/SHA入口及原账本可用；真实服务未配置/未验证 | frozen-configured-adapter测试 |
| 1/3/10批次 | 不同PID、实际V2 Fake Job、共享账本和逐商品回读通过 | batch测试及保留证据 |
| 真实效果/准确率/线上 | 本轮NOT RUN，未达到生产门槛 | 37组证据矩阵 |

逐项来源与限制见 v2-followup-requirement-matrix.md；不能把代码或文件存在等同于真实阶段完成。
