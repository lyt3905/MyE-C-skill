# V2包装盒分类准确率

## 当前：Q01–Q24已授权真实只读回归

Q01–Q24的24张本地原图真实只读回归已结束：47次请求（仅DeepSeek/MiMo，无重试），最终动作REVIEW 23、KEEP 1；取得有效输出44条、未取得有效输出3条（含请求失败和格式错误）。本批网关已知Token 350370，未知usage 1次，费用null，仅记录。线上访问、上传、保存、删除和本地整改均0。完整目标仍未完成。

最新结果入口v2-qbatch-acceptance.md。805项离线测试源绑定未变；17份报告的以下旧记录均按原日期和源码检查点保留。OpenCV/完整LaMa已配置，普通本地去字不需要外部编辑配置。

本批包装分类属于真实模型观察，但无独立包装盒真值，盒/无盒准确率仍NOT EVALUATED，不从水印标签推断。

## 前轮本地记录（历史原文保留）

最新完整离线回归：795 项通过，失败/错误/跳过均为0；run_id=1b76237b9bee4738a13a44366b72b38b。测试期间源码一致，无网络尝试；本轮真实模型调用及线上写入0。详见 v2-evaluation-full-tests.log、v2-evaluation-tests-status.json 和 v2-evaluation-test-source-manifest.json。783 项记录仅作为上一版源码历史检查点保留。

NOT EVALUATED。有盒/无盒独立人工确认样本各0，未达到各30。两方向误判率与有盒/无盒SKU选图准确率分别保持null。

本地程序已验证盒关系、置信、同框优先、不同SHA/角度、适用性、真实SKU ID与池写入；Fake输出不是模型真实识别运输箱、背景盒或玩具部件的证据。

## 离线评估能力补齐

既有 shadow_evaluate.py 新增 --v2，按图片SHA跨位置去重，五动作、暂缓、严重错误及修复结果分别统计，包装双向误判及SKU有盒/无盒分别评分。文档：docs/v2-offline-evaluation.md。空真实数据 reports/v2-evaluation-empty-real.json 状态 NOT_EVALUATED；合成样例 reports/v2-evaluation-synthetic.json 状态 SYNTHETIC_ONLY，不计真实样本。工具不认证人工来源、不授予真实操作权限，REMOVE_TEXT通过率门槛须显式配置。
