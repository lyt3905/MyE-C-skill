# 当前：Q01–Q24真实只读回归已执行

Q01–Q24的24张本地原图真实只读回归已结束：47次请求（仅DeepSeek/MiMo，无重试），最终动作REVIEW 23、KEEP 1；取得有效输出44条、未取得有效输出3条（含请求失败和格式错误）。本批网关已知Token 350370，未知usage 1次，费用null，仅记录。线上访问、上传、保存、删除和本地整改均0。完整目标仍未完成。

24张中16张有明确水印二元标签：TP=0、FP=2、TN=1、FN=0，阳性暂缓7、阴性暂缓6；另8张无二元真值。已作出二元结论3/16，不能把暂缓当正确、也不能用二元结果替代五动作准确率。 此处是预先固定的字段投影，不是模型原生的第三方归属结论。Q12/Q22投影与标签冲突（FP）：两模型原始动作均KEEP，理由明确识别为原厂品牌/型号信息，但将部分文字记为PROMOTIONAL_TEXT，导致固定规则投成阳性；程序最终均REVIEW。保留这两条评分冲突，不事后改规则来提高分数，也不把它们描述为实际误删或误擦。此投影存在类别与第三方归属不完全对齐的限制，不能单独当作原生水印准确率。

10张有明确整图DELETE真值，最终DELETE 0、暂缓10、其他不匹配动作0。具体非DELETE结果逐图列出；不把暂缓计作误删，不把保守暂缓计为删图成功。包装、SKU选择、REMOVE_TEXT修复与AI_REGENERATE没有相应新人工真值/执行证据，准确率门槛仍未通过。

联合旧标签覆盖27/47，剩余20张无当前真实预测。最新报告reports/v2-qbatch-acceptance.md；本批独立Job、账本、实际提示词、原始回复均保留。不继续调用或线上写入；源码及805项测试绑定不变。

## 历史状态（原文保留）

# 最新状态：2026-11-15 V2 离线评估续作

最新完整离线回归：795 项通过，失败/错误/跳过均为0；run_id=1b76237b9bee4738a13a44366b72b38b。测试期间源码一致，无网络尝试；本轮真实模型调用及线上写入0。详见 v2-evaluation-full-tests.log、v2-evaluation-tests-status.json 和 v2-evaluation-test-source-manifest.json。783 项记录仅作为上一版源码历史检查点保留。

完整目标未完成；真实Shadow、人工真值准确率、真实编辑效果、线上Canary及生产验收未通过。本轮仅本地开发，Token仅记录，门槛0.80，仅DeepSeek/MiMo。最新入口：reports/v2-evaluation-acceptance.md。以下保留历史记录，旧真实权限不适用于当前轮次。

# 当前项目状态

## 最新：剩余主流程已补齐，PID5097两处拼版已删除

- 最终Job JOB_04845d393ca34eb1be3dc4207ca0571c；Shop7/shana1、PID5097。主图/详情图池首张装饰拼版已整图删除，各6→5，SKU图仍2；1次保存、0上传/翻译/状态/发布。
- 独立API读取及10个保留URL逐字节核验通过；完整SKU和所有非图片字段（含Description原类型原值）不变，其他图池不变。全程接口，无浏览器操作。
- 剩余14条暂缓引用记录对应5份独立内容，文字归属、截断标记及2份身份仍有真实不确定；当前PARTIALLY_AUTO_FIXED，未宣称全商品审核整改完成。
- 装饰拼版整图复核优先于裁边；允许在包装素材另有留存时移除含盒面的自制拼版；多张拼版不能互相作保留素材；普通盒照/官方摄影保护。
- 已验证的SKU现有引用不因缺数据库ID重复暂缓；实际重分派仍使用已有快照行绑定。未授权标题/品牌问题排除图片整改；暂缓按独立图片内容分组。
- 审核统计冻结为full_audit_run_metrics.json，报告可合法更新运行统计；旧失败Job/原始响应/账本完整保留，新Job完成真实验收。
- 最终完整Fake/Mock回归729项全通过（0失败/0错误/0跳过，源码测试期间未变），compileall/Diff检查通过。原433项证据及旧SKU11文件封印不变。
- 仅deepseek-v4.1-flash与mimo-v2.6-pro，门槛0.80；本轮65次真实请求，已知网关393883 Token，3次用量未知，总量null；仅记录。
- 最终入口：reports/finish-5097-implementation.md；独立复验：reports/finish-5097-independent-readback.json；剩余图片：reports/finish-5097-remaining-items.md。
- 当前HEAD20ecfe83e307bbe15e7e298954a7c57d90dcdca6，原分支/本地修改保留；无子Agent、add/commit/push。

## 最新：全部模型置信度门槛0.80

- 用户要求所有模型置信度门槛降至0.80；分类、水印、身份、SKU、删除与整改复核统一引用policy_engine.MODEL_CONFIDENCE_MIN。
- 0.80边界测试5项、相关回归97项及最终完整回归722项全部通过；0失败/0错误/0跳过，源码测试期间未变。未新增真实模型调用或线上写入。
- 历史41次真实请求完整文字已从执行归档还原，41/41与账本提示词哈希一致；见reports/8788-historical-prompts.md。
- 历史删除提示词保护商品照片、包装和有用信息，不会仅因水印批准整图删除；该业务策略尚未随置信度变更而改写。
- 本次变更与最终测试见reports/confidence-080-change.md。

## 最新补充：2026-11-14 模型选择与范围澄清

- 仅使用deepseek-v4.1-flash与mimo-v2.6-pro；默认客户端、网关配置和验证入口同步，HTTP发送处拒绝其他模型，无自动回退。
- 本次未新增真实模型调用或线上写入；旧真实结果仍归属旧模型组合，新组合尚未真实复验。
- 上轮完整审核覆盖6主图+6详情图+2 SKU图+2 SKU引用，去重6图、14任务；只完成两处首图整改，不是只审核首图。
- 详见reports/model-selection-and-audit-coverage.md及model-selection-two-models-tests.log。

## 2026-11-14 正常主流程推进（模型切换前验收）

- 用户指令调整：Token仅记录；先完成正常主流程；授权shana1/Shop7/PID5097全部图片整改动作，不外部找图。
- 正常CLI默认RECORD_ONLY，Token/请求/图片累计及usage缺失不阻断，费用无依据记null。原STRICT/CONTROLLED显式模式保留。
- 本轮真实主流程已完成main[0]/detail[0]横幅裁边，1上传1保存，独立线上字节回读一致；非图片字段及SKU不变。
- 最终PARTIALLY_AUTO_FIXED，保留20条暂缓记录；没有宣称全图审核完成。
- 修复：已确认mark与同图未知项分开处理；800px原图裁边后可白底补方；修复范围绑定到质量检查；通过质量门禁的候选以独立线上字节一致性验收。
- 本轮41次真实请求，网关报告223943 Token，仅记录不做优化。
- 定向主流程及最终完整Fake/Mock回归714项通过，0失败/0错误/0跳过；无网络尝试，测试期间源码未变。compileall、Diff检查与433项历史证据及旧SKU11文件复核通过。
- 当前HEAD20ecfe8及分支保留，无add/commit/push，无子Agent；本轮开始时的全部既有代码改动保留。
- 最新真实结果：reports/mainflow-5097-real-remediation.md；用量：reports/mainflow-record-only-usage.json。

## 上一轮本地验收（历史记录）


2026-11-14T20:30:55.274703+08:00；HEAD 20ecfe83e307bbe15e7e298954a7c57d90dcdca6；基准a14669b。初始项目tree相同，当前分支不回退；仓库外部已有修改逐字节保留。

阶段A/B/C/D本地工作完成；完整Fake/Mock回归708通过、标准入口复验通过，compileall/Diff/源码绑定及433证据哈希复核通过。预算与完整审核桥接为IMPLEMENTED/FAKE_VERIFIED。

真实模型请求/新Token/站点读写/真实整改全0；STRICT仍PREFLIGHT_BLOCKED，受控Canary enabled=false、价格与USD授权未知。真实Shadow/真实Canary NOT RUN；本轮无新增REAL_VERIFIED或PRODUCTION_READY。

Description旧解析例外已移除，原值原类型严格保护。5097两份历史SKU响应离线重放REVIEW/UNKNOWN，原观察和封印未变。

完整入口：reports/automation-final-acceptance.md；业务调用链与缺口矩阵、12份报告及日志在reports/。没有子Agent、add/commit/push。gpt-6.1-sol在本地桌面模型目录可见，项目配置已写入；未声称运行中的会话权限/模型已切换。

下一步：用户确认新Job只读Shadow预算和范围前保持停用；真实写入/回滚另行独立授权。

本次切换后相关本地回归128项全部通过（293.232秒），compileall及git diff --check通过。该结果为相关测试集，未宣称重新运行全部714项。首次回归暴露验证入口仍默认读取历史模型配置，修复默认路径后重新通过；首次失败日志保留。
# 2026-11-15 V2.0 本地开发（历史段落保留）

## V2.0 续作当前状态

- 新增23项回归，当前总计783项通过，失败/错误/跳过均为0；源文件测试前后及交付核对一致。760与774是历史检查点。
- 已补齐：修复图SKU上传地址回读、真实ID缺失时保留SKU引用、仅引用图片修复与删除、删图同步SKU重绑、保留最后包装证据及其字节回读、两张无盒图进入SKU池、配置式重绘适配器、LaMa双输入契约和RGBA透明度保护。
- run/full-audit默认V2，legacy显式指定；V2的1/3/10商品Fake批次、跨Job幂等及未知结果停止均已验证。
- 本轮保留23个完整Fake Job、1163个证据文件，见 reports/v2-followup-retained-fake-jobs.json。无真实模型或线上写入。
- 完整目标继续保持未完成：真实Shadow、独立人工标注准确率、线上Canary、实际编辑后端与真实LaMa权重/效果及生产门槛仍缺。不得标记PRODUCTION_READY。
- 当前验收入口：reports/v2-followup-acceptance.md；逐项证据矩阵：reports/v2-followup-requirement-matrix.md。旧报告/日志作为历史记录保留。

- HEAD：20ecfe83e307bbe15e7e298954a7c57d90dcdca6；工作分支 codex/8788-contract-local-fix-20261114。
- 改动前源文件副本与 SHA：work/v2-local-20261115/baseline（435 份），未覆盖已有修改，未暂存/提交/推送。
- V2 新策略接入既有 Runner、完整审核、模型客户端、预算、SKU、候选编译、执行器与回读；默认 run 使用 V2，旧 Job 兼容。
- 统一视觉五动作；每 SHA 主模型一次，条件独立第二模型。V2 无 OCR/CV 语义分类；归一化 mask 与 OpenCV/可选本地 LaMa；授权配置与真实 SKU ID 绑定。
- 用户覆盖：0.80 / DeepSeek+MiMo / Token 仅记录；本轮无真实模型、无线上写入。
- 未配置可用 LaMa 权重；真实编辑后端未接入；无盒同一 SKU 两张图仅逻辑选图，站点目前单 URL 能力限制如实暂缓。
- 测试最终状态与源绑定见 reports/v2-local-tests-status.json；本轮验收入口 reports/v2-final-acceptance.md。未达到 PRODUCTION_READY；真实 Shadow、Canary、独立标注准确率均未执行。


V2.0 最终本地回归：760项通过（原729项 + 新31项），0失败/错误/跳过；源文件测试前后及交付核对一致。compileall和git diff --check通过；历史433+11份证据未变；保留8个完整Fake场景/385文件。见 reports/v2-final-acceptance.md。
