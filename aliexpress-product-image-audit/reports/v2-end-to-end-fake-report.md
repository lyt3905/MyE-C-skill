# V2完整Fake回归

## 当前：Q01–Q24已授权真实只读回归

Q01–Q24的24张本地原图真实只读回归已结束：47次请求（仅DeepSeek/MiMo，无重试），最终动作REVIEW 23、KEEP 1；取得有效输出44条、未取得有效输出3条（含请求失败和格式错误）。本批网关已知Token 350370，未知usage 1次，费用null，仅记录。线上访问、上传、保存、删除和本地整改均0。完整目标仍未完成。

最新结果入口v2-qbatch-acceptance.md。805项离线测试源绑定未变；17份报告的以下旧记录均按原日期和源码检查点保留。OpenCV/完整LaMa已配置，普通本地去字不需要外部编辑配置。

## 前轮本地记录（历史原文保留）

最新完整离线回归：795 项通过，失败/错误/跳过均为0；run_id=1b76237b9bee4738a13a44366b72b38b。测试期间源码一致，无网络尝试；本轮真实模型调用及线上写入0。详见 v2-evaluation-full-tests.log、v2-evaluation-tests-status.json 和 v2-evaluation-test-source-manifest.json。783 项记录仅作为上一版源码历史检查点保留。

当前完整标准入口回归与源绑定见v2-followup-tests-status.json及v2-followup-test-source-manifest.json。23项续作回归补齐：已解析SKU地址、两个候选入池、模型适用性、仅引用图片修复/删除/暂缓、缺ID的独立修复、删除后SKU同步重绑、保留盒材料与内容漂移、配置式编辑、重绘身份失败、RGBA、两种TorchScript契约、full-audit默认V2、1/3/10真实V2 Fake Job、跨Job幂等和未知结果停止批次。

保留23个Fake Job、1163文件，含1/3/10批次的14个不同PID。根目录work/v2-followup-20261115/evidence，各Job有逐文件archive清单，原始临时目录与副本见v2-followup-retained-fake-jobs.json；副本内容与原Job字节一致，未重写授权/原始响应。

这些调用/保存是本地Fake协议与内存站点，不是线上操作。SITE_SINGLE_IMAGE_REFERENCE、缺ID和真实能力未配置继续显示部分完成/暂缓；没有被改成全量成功。保留图内容漂移正确失败且保存不重发。

760和774分别是前两个源码检查点，原日志和原源码快照保留；不可用旧manifest替代当前代码证明。早期D盘持久化示例曾遇到文件替换拒绝访问，根因未修复；当前完整回归包含D盘相对目录案例但不能证明该环境问题永不发生。
