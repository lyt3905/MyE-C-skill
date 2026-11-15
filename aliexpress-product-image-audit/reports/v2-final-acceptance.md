# V2.0 当前验收与目标状态

## 当前：Q01–Q24已授权真实只读回归

Q01–Q24的24张本地原图真实只读回归已结束：47次请求（仅DeepSeek/MiMo，无重试），最终动作REVIEW 23、KEEP 1；取得有效输出44条、未取得有效输出3条（含请求失败和格式错误）。本批网关已知Token 350370，未知usage 1次，费用null，仅记录。线上访问、上传、保存、删除和本地整改均0。完整目标仍未完成。

最新结果入口v2-qbatch-acceptance.md。805项离线测试源绑定未变；17份报告的以下旧记录均按原日期和源码检查点保留。OpenCV/完整LaMa已配置，普通本地去字不需要外部编辑配置。

24张中16张有明确水印二元标签：TP=0、FP=2、TN=1、FN=0，阳性暂缓7、阴性暂缓6；另8张无二元真值。已作出二元结论3/16，不能把暂缓当正确、也不能用二元结果替代五动作准确率。 此处是预先固定的字段投影，不是模型原生的第三方归属结论。Q12/Q22投影与标签冲突（FP）：两模型原始动作均KEEP，理由明确识别为原厂品牌/型号信息，但将部分文字记为PROMOTIONAL_TEXT，导致固定规则投成阳性；程序最终均REVIEW。保留这两条评分冲突，不事后改规则来提高分数，也不把它们描述为实际误删或误擦。此投影存在类别与第三方归属不完全对齐的限制，不能单独当作原生水印准确率。

10张有明确整图DELETE真值，最终DELETE 0、暂缓10、其他不匹配动作0。具体非DELETE结果逐图列出；不把暂缓计作误删，不把保守暂缓计为删图成功。包装、SKU选择、REMOVE_TEXT修复与AI_REGENERATE没有相应新人工真值/执行证据，准确率门槛仍未通过。

阶段G只读批次已执行，准确率门槛未通过；H本轮NOT RUN，I未完成；当前HEAD20ecfe83e307bbe15e7e298954a7c57d90dcdca6。

## 前轮本地记录（历史原文保留）

最新完整离线回归：795 项通过，失败/错误/跳过均为0；run_id=1b76237b9bee4738a13a44366b72b38b。测试期间源码一致，无网络尝试；本轮真实模型调用及线上写入0。详见 v2-evaluation-full-tests.log、v2-evaluation-tests-status.json 和 v2-evaluation-test-source-manifest.json。783 项记录仅作为上一版源码历史检查点保留。

完整目标保持进行中，尚未证明全部完成。当前证据支持本地实现/Fake验证；真实Shadow、独立人工准确率、线上Canary及生产门槛仍未满足，本轮禁止自动执行真实模型调用和线上写入。

## 当前已验证

- 标准脚本scripts/run_auto_tests.ps1：795项通过，失败0、错误0、跳过0。
- 运行ID：1b76237b9bee4738a13a44366b72b38b；耗时633.437秒。测试前后源码一致，交付时再次核对匹配。compileall、git diff --check及CLI help检查通过。
- 从760项检查点先补充23项，再新增12项离线评估测试，共795项；760/774/783日志作为各自源码的历史检查点保留。
- 保留23个完整Fake Job、1163文件，包括V2的1/3/10商品批次。原433+11份历史证据SHA未变。
- 真实图片审核模型调用0、线上上传/保存/发布0。Fake调用及synthetic TorchScript计算不作为真实模型效果或供应商账单。

## 本次实际补齐

1. 修复图被选为SKU图后，按上传完成后的真实地址核对，避免成功整改误报失败。
2. 两张无盒候选都进入已支持的images.sku池；尊重适用性、不同SHA/角度与已有正确引用。单SKU双引用能力仍未核实，不伪造接口字段。
3. 仅出现在SKU引用里的图片也可修复、上传并绑定已有真实ID；REVIEW留明确记录，授权DELETE可通过SKU换引用完成。
4. 删图和SKU替代在同一次保存中完成；必需重绑没在实际计划里时拒绝删除。缺真实ID时原SKU引用保持不变，独立主/详情修复可以继续。
5. 最后一份同商品包装证据保留；有保留材料时装饰图可删除，并回读保留图的实际SHA。内容漂移不报通过、不重发保存。
6. image_options支持固定本地适配器路径、SHA和已选模型，真实调用仍走原JudgeClient/BudgetManager。真实编辑服务尚未配置/核实。
7. LaMa适配器兼容已安装依赖的双Tensor及字典契约，合成TorchScript验证padding/输出；RGBA修复保留mask外透明度。未找到完整真实LaMa权重，未下载。
8. run与full-audit均默认V2，不要求OCR模板；legacy显式选择。跨Job幂等和未知结果停止批次已走实际V2 Fake链路。

## 未完成及证据边界

| 项目 | 当前状态 | 完成所缺证据 |
|---|---|---|
| 真实编辑/LaMa效果 | 未验证 | 已配置可用能力与真实输出质量；当前只验证接口/合成图 |
| G真实只读Shadow | NOT RUN | 新的明确真实范围/授权、有效配置及对应预算条件 |
| 动作和包装准确率 | NOT EVALUATED | 独立人工真值；DELETE/REMOVE_TEXT/AI_REGENERATE各至少30、盒/无盒各至少30及各自门槛 |
| H线上单商品Canary | NOT RUN | G及准确率门槛、新Shop/PID/动作授权与独立真实回读 |
| I生产准备 | NOT PRODUCTION_READY | 真实批量、恢复/预算实证和独立生产审查 |

不能把Fake通过、配置文件存在或旧PID5097真实结果当作上述阶段完成。Token仅记录、统一0.80、仅DeepSeek/MiMo的用户偏好保留；未知usage/费用不编造为0，严格模式能力与本轮记录模式分别说明。

早期D盘证据示例的原子文件替换拒绝访问根因尚未定位，不能声称已经修复；当前回归包含相对路径案例且通过。新的保留证据先在独立临时目录完成，再逐文件校验归档。

## 交付入口

- 当前完整日志/状态/源绑定：v2-evaluation-full-tests.log、v2-evaluation-tests-status.json、v2-evaluation-test-source-manifest.json。
- 逐项证据和剩余门槛：v2-followup-requirement-matrix.md/json；原文条目提取：v2-followup-spec-items.json（含重复要求和命令示例）。
- 保留Job与批次：v2-followup-retained-fake-jobs.json；本地样本和mask：work/v2-followup-20261115/samples；Fake证据：work/v2-followup-20261115/evidence。
- 适配器契约：docs/image-edit-adapter-v2.md；依赖/权重检查：v2-followup-local-runtime.json。
- 本次增量：v2-followup-incremental.patch；当前累计：v2-followup-cumulative.patch；文件/交付哈希：v2-followup-delivery-manifest.json。
- 首轮760报告/源文件副本保留于work/v2-followup-20261115/baseline/files；760/774的manifest对应各自历史代码，不应直接对当前树验证。

任务书要求的17份报告均已更新，G/H明确NOT RUN；本报告和v2-followup-acceptance.md为当前入口。HEAD仍为20ecfe83e307bbe15e7e298954a7c57d90dcdca6，未暂存/提交/推送，未覆盖历史Job、响应或账本，未创建子Agent。目标保持active，不以本地阶段替换完整目标。

## 补丁交付复验

增量补丁已改为Git生成，避免CRLF重复转义和无末尾换行引起的损坏。使用 git -c core.autocrlf=false apply 在隔离临时副本中检查并实际应用，39个目标文件逐字节一致。项目工作区未应用补丁，应用源码及795项测试绑定不变。详见 v2-evaluation-patch-verification.json；无效旧补丁仅保留为 work/v2-evaluation-20261115/incremental-before-packaging-fix.patch 历史副本。
