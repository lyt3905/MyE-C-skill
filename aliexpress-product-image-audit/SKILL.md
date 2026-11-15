# 2026-11-16 同一原图不同版本：替换优先（本地实施）

- 用户最新规则：已有审核KEEP且干净、尺寸格式可用的同一照片版本优先REPLACE_TWIN；没有可替换版本时，大面积店铺宣传边框整图DELETE，其余明确覆盖字局部修复。原始AI回复不改写，报告分别保留初审和最终整改动作。
- 正式V2全图审核后输出full_visual_versions.json，采用SIFT/RANSAC、有效画面覆盖、中心主体与稠密像素对齐证明同照片；不是目录同款/配色判断，模型置信度仍仅记录。仅同背景或同商品不同姿势不匹配。候选限当前商品已有KEEP干净图，未外部找图。
- 复用既有REPLACE_TWIN执行器和SHA内容组；同步主图/详情/正文商品图/SKU池与可定位SKU引用、受限保存、独立字节回读。替换使用已有URL零上传，不运行擦除质量模型；已有全图初审作为候选干净依据。footer、正文文字/样式、其他业务字段继续保护。
- 大边框根据AI已有店铺/促销覆盖区域的联合面积和边缘分布组合识别，不再仅依赖OTHER_STORE_FRAME标签；可用照片上的小店铺标记不因该标签直接整删；旧观察只圈文字时，明确边框的宣传拼图也按底部店铺/促销横幅的跨度判断，保留5085已确认删除案例。无法证明可替换不等于证明不同照片，回落原整改流程。
- 本轮只做本地开发、离线原图验证和Fake闭环；新真实模型调用、线上读取/上传/保存均NOT_RUN，未部署、未commit/push，旧Jobs/响应/账本保留。外部AI重绘仍后置，其他历史语义偏差未在本轮解决。
- 证据入口：reports/v2-visual-versions.md；work/v2-visual-versions-20261116。下方历史授权/规则按各自时间和范围理解。

> 最新用户规则（2026-11-15，经验复用）：正式V2初审及质量复核仅DeepSeek；全部置信度、Token、型号/结构/配色及box_relation仅记录。纯卖家介绍/须知图删除；明确其他店铺边框整图删除；明确后加水印进入本地去除，即使owner仍UNKNOWN，不能当普通未知文字放行。普通未知文字、厂家印刷与创作者署名保留。正文商品图片和同SHA的全部不同链接纳入统一审核/计划/保存/回读；shopFooter附加内容、正文文字及其他业务字段保留。两张无盒图可分别绑定现有无盒/有盒SKU。真实调用和线上写入仍按独立授权，不重跑旧Job、不改原始响应/账本、不擅自commit/push。[本轮验证](reports/v2-reusable-image-rules.md)。下文冲突的整体Description排除、双模型、0.80和同款门槛均按历史理解。

> 历史V2闭环入口与验收：[完整业务流程报告](reports/v2-full-workflow-acceptance.md)。完整LaMa已安装并真实本地推理，AI编辑仅已配置适配器才调用。

> 当前有效范围：[V2图片池、SKU引用和正文商品图片，尾部与文字保护](references/当前有效审核范围.md)。

---
name: aliexpress-product-image-audit
description: 商品自动审核与整改；本地白名单授权执行，独立质量复检，异常逐项暂缓。
---

# 商品自动审核与整改

标准入口（同一 --root）：
```powershell
python scripts/workflow_runner.py run --pid PID --shop SHOP --mode audit --root work/v2
python scripts/workflow_runner.py run --pid PID --shop SHOP --mode dry_run --site-config local/site.json --root work/v2
python scripts/workflow_runner.py run --pid PID --shop SHOP --mode auto_apply --automation-config local/automation.v1.json --site-config local/site.json --root work/v2
python scripts/workflow_runner.py status --job JOB_ID --root work/v2
python scripts/workflow_runner.py report --job JOB_ID --root work/v2
```

使用安装了 Pillow、OpenCV、numpy、RapidOCR 等依赖的 Python。只读审核配置通过 AE_READONLY_SITE_CFG 显式提供。audit/dry_run 不写站；auto_apply 必须读取独立本地启用的授权配置，校验 Shop/PID/动作白名单/预算/哈希，不能凭命令名称获权。示例在 scripts/config/automation.v1.example.json，本地配置不入库。

业务规则仍以 references/SOP-商品图片整改.md、SOP-商品标题重写.md、判例与陷阱.md 为依据；新授权说明见 references/自动化执行策略补充.md。AI 只提供观察与证据，Python 编译计划。整改候选通过独立质量门禁才可自动执行，不确定项目保留原样并 DEFERRED。人工 review-submit 保留为异常处理入口。

内容保存最多一次，保持商品状态、价格、重量、运费和原始标题；禁止状态推进、发布与裸 PUT。外部找图默认关闭；删除和擦除由独立开关控制，不能误删盒照或官方/社交署名。写后必须回读，剩余问题报告 PARTIALLY_AUTO_FIXED，不能冒充全图干净。

每件报告在 --root/JOB_ID/report.md，证据/计划/授权/快照/回执保留在同目录。APPLY_UNKNOWN 时先只读回读，不重试 PUT 或自动回滚。旧 read_only、手工 apply 和独立执行器入口继续保留。

当前开发版尚未完成完整自动化验收，已实现与未接入功能以 reports/auto-v1-implementation.md 为准；在完整 Fake 矩阵和只读 Canary 验收前不要启用生产 auto_apply。


恢复与回滚：recover-readback、verify-saved仅核对；retry-translation受总次数2限制且不重新save。rollback-preview生成绑定当前快照的恢复预案，rollback-apply要求显式确认文件，仅恢复原任务内容字段，rollback-readback处理未知结果。不能删除账本绕过限制。

模板配置使用--template-config；必需模板缺失不算通过，明确无适用模板才可配置no_applicable_shop_ids。BOX_NORMALIZE为独立默认关闭权限，完整执行仍须盒照/型号/SHA观察与生成图复检。Windows测试入口：scripts/run_auto_tests.ps1；依赖见requirements-auto.txt和requirements-dev.txt。
