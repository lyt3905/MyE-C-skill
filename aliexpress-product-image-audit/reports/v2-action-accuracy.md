# V2动作准确率

## 当前：Q01–Q24已授权真实只读回归

Q01–Q24的24张本地原图真实只读回归已结束：47次请求（仅DeepSeek/MiMo，无重试），最终动作REVIEW 23、KEEP 1；取得有效输出44条、未取得有效输出3条（含请求失败和格式错误）。本批网关已知Token 350370，未知usage 1次，费用null，仅记录。线上访问、上传、保存、删除和本地整改均0。完整目标仍未完成。

最新结果入口v2-qbatch-acceptance.md。805项离线测试源绑定未变；17份报告的以下旧记录均按原日期和源码检查点保留。OpenCV/完整LaMa已配置，普通本地去字不需要外部编辑配置。

10张有明确整图DELETE真值，最终DELETE 0、暂缓10、其他不匹配动作0。具体非DELETE结果逐图列出；不把暂缓计作误删，不把保守暂缓计为删图成功。包装、SKU选择、REMOVE_TEXT修复与AI_REGENERATE没有相应新人工真值/执行证据，准确率门槛仍未通过。

24张中16张有明确水印二元标签：TP=0、FP=2、TN=1、FN=0，阳性暂缓7、阴性暂缓6；另8张无二元真值。已作出二元结论3/16，不能把暂缓当正确、也不能用二元结果替代五动作准确率。 此处是预先固定的字段投影，不是模型原生的第三方归属结论。Q12/Q22投影与标签冲突（FP）：两模型原始动作均KEEP，理由明确识别为原厂品牌/型号信息，但将部分文字记为PROMOTIONAL_TEXT，导致固定规则投成阳性；程序最终均REVIEW。保留这两条评分冲突，不事后改规则来提高分数，也不把它们描述为实际误删或误擦。此投影存在类别与第三方归属不完全对齐的限制，不能单独当作原生水印准确率。

## 前轮本地记录（历史原文保留）

最新完整离线回归：795 项通过，失败/错误/跳过均为0；run_id=1b76237b9bee4738a13a44366b72b38b。测试期间源码一致，无网络尝试；本轮真实模型调用及线上写入0。详见 v2-evaluation-full-tests.log、v2-evaluation-tests-status.json 和 v2-evaluation-test-source-manifest.json。783 项记录仅作为上一版源码历史检查点保留。

NOT EVALUATED。独立人工确认样本为0。DELETE至少30独立样本、精确率≥98%、严重误删0的发布门槛尚未满足；REMOVE_TEXT定位/修复门槛及关键结构损伤0、AI_REGENERATE身份/结构严重错误0也没有真实样本证明。

KEEP/REVIEW/各动作准确率、严重错误率、暂缓率均不从Fake测试推定。蓝色矩形/合成TorchScript和重复SHA不计真实独立样本。真实标签和模型输出未取得，不能伪造比例或PRODUCTION_READY。

## 离线评估能力补齐

既有 shadow_evaluate.py 新增 --v2，按图片SHA跨位置去重，五动作、暂缓、严重错误及修复结果分别统计，包装双向误判及SKU有盒/无盒分别评分。文档：docs/v2-offline-evaluation.md。空真实数据 reports/v2-evaluation-empty-real.json 状态 NOT_EVALUATED；合成样例 reports/v2-evaluation-synthetic.json 状态 SYNTHETIC_ONLY，不计真实样本。工具不认证人工来源、不授予真实操作权限，REMOVE_TEXT通过率门槛须显式配置。
