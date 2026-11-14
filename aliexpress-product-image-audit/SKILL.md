> 当前有效范围：[仅主图、详情图、SKU图；Description原值保护](references/当前有效审核范围.md)。此规则覆盖下文历史Description联动口径。

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
