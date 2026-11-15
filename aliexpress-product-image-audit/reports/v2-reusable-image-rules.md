# V2 图片审核经验复用验收

本轮唯一目标：把用户在4086/5085纠正的问题固化到现有正式V2调用链。单Agent，本地开发、离线真实本地算法和Fake验证；真实模型请求、线上商品读取/上传/保存均0。没有commit或push，没有改写旧Job、原始模型回复和账本。

## 结果与边界

| 功能 | 实现/本地验证 | 新版真实模型/线上验收 |
|---|---|---|
| 纯卖家介绍、购买/售后须知图整图删除 | IMPLEMENTED / FAKE_VERIFIED | NOT_RUN |
| 明确其他店铺边框主图整图删除，原KEEP与规则纠正分别保留 | IMPLEMENTED / FAKE_VERIFIED | NOT_RUN |
| 明确后加水印即使owner UNKNOWN也进入修复，普通未知文字保留 | IMPLEMENTED / FAKE_VERIFIED | NOT_RUN |
| 置信度、Token与同款关系仅记录，包括box_relation及SKU选图 | IMPLEMENTED / FAKE_VERIFIED | NOT_RUN |
| 正文商品图采集/审核，正文独有图与有标记边界的混合图片块 | IMPLEMENTED / FAKE_VERIFIED | NOT_RUN |
| 内容SHA别名分组、统一模拟、上传去重、一次保存与独立回读 | IMPLEMENTED / FAKE_VERIFIED | NOT_RUN |
| footer/正文文字/样式/非图片字段保护，读取失败不当作通过 | IMPLEMENTED / FAKE_VERIFIED | NOT_RUN |
| OpenCV背景字形精修与真实训练LaMa本地执行 | IMPLEMENTED / FAKE_VERIFIED；3份本地LaMa输出的像素行为REAL_VERIFIED | 新候选语义质量NOT_RUN |
| 新版部署到线上审核服务、真实新商品自动整改验收 | NOT_RUN | NOT_RUN |

已接入正式入口，不再依赖PID5085的一次性发布脚本。未把Fake通过或历史线上整改当作本版本PRODUCTION_READY。

## 规则与生产链

1. image_action_decision提示词/Schema新增可选overlay_role和repair_mode。OTHER_STORE_FRAME走DELETE，SELLER_NOTICE在无商品/包装且不含有用商品资料时走DELETE，ADDED_WATERMARK进入本地修复。规则纠正写入policy_adjustments，results保留原模型动作和UNKNOWN/HIGH/低分，不伪造原判断。
2. 厂商标识、型号/商品印刷、包装文字与创作者署名按语义kind和owner双重保护，不能用错误叠加的ADDED_WATERMARK标签解禁。普通未知文字不因UNKNOWN被擦除，有用尺寸图不当卖家通知删掉。
3. download_only和run_unified_audit采集正文商品图片，build_inventory保留description_image业务位置，并按原始字节SHA与图片池/SKU去重。正文文字不发模型；shopFooter及之后内容不采集、不整改。正文独有图片不伪造线上图片池位置。
4. prepare/compile_auto_plan为获准动作建立content_groups；final_state、ExecutorService、受限SiteWriteClient保存通道与verify_content共同使用这一计划。相同内容不同URL同步到主图/详情/正文及已授权可定位的SKU引用；一次上传去重、一次保存。
5. 不能定位的旧SKU引用保留并明确暂缓，不阻止独立主图修复，也不把该商品报为全部完成。会删空必需图片池或破坏SKU的删除不能靠另一处引用绕行。
6. 背景淡水印按字形像素精修，保留真实HIGH观测；不擦除HIGH整个矩形。粗略整件玩具保护框可显式标PRODUCT_FOREGROUND，只在无包装、平滑背景且连接边缘的近白背景细化；精确印刷/标识保持EXACT_REGION。RGBA掩膜外精确保留，alpha原样保留。质量失败不上传，外部AI重绘仍后置。
7. 最终回读同时检查正文计划结果、正文图片字节、图片池/SKU字节及所有非图片业务字段。正文文字、footer或旧别名回读出错时不能通过，即使其他图片池已正确。

标准路径：workflow_runner run/full-audit → full_product_audit.run_unified_audit → v2_remediation.prepare → plan_compiler → final_state → ExecutorService → SiteWriteClient → v2_remediation.verify_content → automatic_report。

## 固定样本和验收数据

tests/fixtures/v2_image_corrections保留8张原始字节图片及标签：4086的3张店铺通知，5085的英文介绍、其他店铺边框和3张淡水印图。labels.json绑定原SHA、原Job/结果文件SHA、用户纠正及原模型观察。用于验证规则遵守已给定的视觉角色；不是新模型预测，不能据此宣称提示词准确率100%。

最终全项目917项离线测试通过，失败/错误/跳过0，网络尝试0。三个独立本地测试进程按模块分配，已验证测试ID多重集无遗漏/无重复分片，所有进程的运行前后456项文件绑定一致。代码/提示词/测试和素材没有在最终测试中变更。

新增20项回归（含8固定样本、多个反例/子场景）。原“POSSIBLY_SAME_PRODUCT必须REVIEW”的过时断言按用户新规则改为KEEP，并加原值保留及retail_box_status UNCERTAIN仍REVIEW的对照；没有删除或放松其余测试。首轮全量暴露的SKU兼容问题已修复；测试子进程PYTHONPATH与新测试缓存目录问题已修正。首轮失败和中断日志原样保留，未冒充最终通过。

## 保留的正式Fake工作流

| 场景 | 最终业务状态 | Fake上传 | Fake保存 |
|---|---|---|---|
| mixed-delete-repair-aliases | PARTIALLY_AUTO_FIXED | 1 | 1 |
| complete-two-sku | AUTO_VERIFIED | 1 | 1 |
| body-only-delete | PARTIALLY_AUTO_FIXED | 0 | 1 |
| body-only-repair | PARTIALLY_AUTO_FIXED | 1 | 1 |
| missing-body | REVIEW_REQUIRED | 0 | 0 |
| quality-failure | REVIEW_REQUIRED | 0 | 0 |
| corrupt-description | APPLY_UNKNOWN | 0 | 1 |

complete-two-sku是从Shop/PID输入开始，到采集、Fake DeepSeek初审、真实本地OpenCV修复、Fake质量复核、SKU分配、Fake上传/一次保存、独立回读及报告的完整AUTO_VERIFIED案例。单SKU图片不足等场景仍如实PARTIALLY_AUTO_FIXED；读取失败/质量失败是REVIEW_REQUIRED，错误保存回读是APPLY_UNKNOWN。

3张历史水印原图还执行了当前本地LaMa，所有像素检查通过；使用单独记录的类型化几何重放注解，不把它伪装成模型新输出。未对这些新候选调用真实DeepSeek质量复核，未上传。

## 交付与证据

- work/v2-reusable-rules-20261115/final-shard-0.log至final-shard-2.log、tests-status.json、test-source-manifest.json、各shard-test-ids.json：完整测试和覆盖证明。
- fake-case-results-verified.json、fake-cases-verified目录：7个可复查的新Fake Job及前后状态，Fake来源明确标识。
- local-replay-results-verified.json、local-replays-verified：3份真实本地LaMa掩膜/候选/像素验证，语义复核NOT_RUN。
- tests/fixtures/v2_image_corrections/labels.json：固定原图及人工纠正来源。
- reports/v2-reusable-image-rules.patch：相对于本轮开始工作区的增量，需在相同基线上审阅，不是直接针对HEAD的补丁；含新增测试素材。
- reports/v2-reusable-image-rules-manifest.json：最终文件/旧证据哈希和Git检查。

已核对305份已封印的旧证据文件保持原样。当前分支和HEAD不变，既有未提交修改与兄弟项目未覆盖。本地正式入口已更新，线上审核服务未部署；下一次真实模型与线上写入仍遵循具体商品授权。
