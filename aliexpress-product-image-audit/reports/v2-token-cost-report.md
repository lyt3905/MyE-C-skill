# V2 Token与费用记录

## 当前：Q01–Q24已授权真实只读回归

Q01–Q24的24张本地原图真实只读回归已结束：47次请求（仅DeepSeek/MiMo，无重试），最终动作REVIEW 23、KEEP 1；取得有效输出44条、未取得有效输出3条（含请求失败和格式错误）。本批网关已知Token 350370，未知usage 1次，费用null，仅记录。线上访问、上传、保存、删除和本地整改均0。完整目标仍未完成。

最新结果入口v2-qbatch-acceptance.md。805项离线测试源绑定未变；17份报告的以下旧记录均按原日期和源码检查点保留。OpenCV/完整LaMa已配置，普通本地去字不需要外部编辑配置。

本批实际每模型请求：{'deepseek-v4.1-flash': 24, 'mimo-v2.6-pro': 23}。累计三轮PID5097与本批请求77；已知Token小计558635，累计总量仅在usage全已知时可确认；USD仍null。质量表含模型行与融合行，Token存在重复视图，不得逐行相加。

## 前轮本地记录（历史原文保留）

最新完整离线回归：795 项通过，失败/错误/跳过均为0；run_id=1b76237b9bee4738a13a44366b72b38b。测试期间源码一致，无网络尝试；本轮真实模型调用及线上写入0。详见 v2-evaluation-full-tests.log、v2-evaluation-tests-status.json 和 v2-evaluation-test-source-manifest.json。783 项记录仅作为上一版源码历史检查点保留。

本轮真实图片审核模型调用0、新增真实审核Token 0、线上上传/保存/发布0。Fake usage是受控测试数据，不能作为供应商账单；USD无已核实依据时为null，SPEND_CAP_GUARANTEED=false。

语义判断、条件第二模型、质量复核及配置式图像编辑都复用同一Job的JudgeClient/BudgetManager。已复现并校准编辑请求计数；缓存与实际调用区别记录。用户Token仅记录覆盖继续有效，不新增Token优化；显式STRICT/受控模式旧停止规则保留，本轮没有以其配置授权真实动作。

Codex本身的目标执行用量与商品网关调用分别记录在续作交付manifest中，不混入真实商品审核Token。
