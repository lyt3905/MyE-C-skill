# P0完整审核与整改集成

日期：2026-11-14T20:30:55.274703+08:00；HEAD 20ecfe83e307bbe15e7e298954a7c57d90dcdca6；基准a14669b。

IMPLEMENTED / FAKE_VERIFIED；本轮REAL_VERIFIED=false、PRODUCTION_READY=false。

默认workflow_runner run的自动阶段复用run_full_audit，同一Job生成完整图片/SKU审核。保留full-audit只读CLI及显式注入旧auditor的Python兼容测试路径。未新建第三套业务Runner、模型客户端或预算账本。

remediation_inputs验证完整证据manifest、Job/Shop/PID、商品state、图片内容/位置/SKU行哈希和Prompt/Schema版本，再按业务位置映射语义结果。SKU数据库ID来自绑定快照，缺失不猜测；原始模型观察/证据ID不改写。Job冻结audit_scope=full，缺权威报告或manifest不能退回窄审核。

UNKNOWN和全局未决生成WEB_DEFER，阻断相关目标及未知SKU分派；确定finding在原报告保留，不能被UNKNOWN覆盖。已确认违规仍需原RemedyPlanner、CandidateQualityGate、remedy_binding、policy授权和写前漂移检查。

Fake确认链路通过：完整审核→整改候选→独立质量→编译→Fake保存一次→字节/SKU/Description回读。已完成Job不再次审核。另覆盖同SHA多位置、错误Job/Shop/state/Prompt、原图及产物篡改、缺权威文件、未知项留存。旧套件覆盖保存未知、跨Job幂等、账号锁、1/3/10件工作流、异常隔离等。

公共JudgeClient真实发送必须经过原BudgetManager新增受控请求表；原STRICT token_budget保持不变。CONTROLLED_CANARY独立Job冻结配置、请求/商品/图片/输出/Token软预留/USD、价格和路由、并发1/重试0，保留raw usage/response与来源。超时/缺usage/账本异常停止；重启悬挂保持UNKNOWN；账本金额篡改拒绝；费用预留失败不发送。关闭重定向与旧HTTP发送入口。没有可用的真实价格或本轮USD授权，示例enabled=false、所有预算待确认值为null。

Description旧标题解析例外与本轮规则冲突，已按明确要求移除：只比较原值原类型，连标题头变化也拒绝。旧允许例外的断言已收紧，未降低任何保护门槛。

验证：708项，失败0、错误0、跳过0；完整离线回归602.922秒，run_id=4b8cc113da9e4dc184e34bde9e3dae2e。标准PowerShell入口执行受保护的同一完整回归并通过（最终日志为同一次运行，不冒充两轮独立样本）。

相对672新增36项（22预算+12桥接+2Description），原测试数量保留。HTTP生成测试补入显式Fake预算；历史Runner测试冻结当前源码到临时Fake基线，不改旧正式manifest；旧CLI夹具显式注入旧auditor继续测原执行器，新增桥接测试覆盖默认完整路径。Description/旧直连测试按新规则收紧。测试数仍包含原有导入重复发现，不等于独立图片或准确率样本数。

早期探索日志存在失败（新守卫与旧夹具冲突、开发期间修改源码触发封印停止）；保留automation-system-exploratory-tests.log及work/automation-system-20261114阶段日志，不作为最终绿结果。复审又发现身份明确错误和直接编译漏带问题可误报CLEAN，新增2项先失败后修复；初轮706绿记录及中止的旧版标准复验另行保留。最终源码冻结后通过标准入口重新完成受保护全量；没有删除、跳过或弱化失败用例。

复现最终Fake回归：在项目目录执行 scripts/run_auto_tests.ps1，使用 -Python 指向相邻ae-img-audit虚拟环境，-LogPath 指向新日志，-TestHarness work/automation-system-20261114/run_offline_tests.py。该harness真实执行unittest discover、阻断网络并校验源码；哈希见automation-final-status.json。默认 -Offline 同样可执行完整unittest，但最终日志所用的是带来源清单的harness。

真实模型/站点请求、真实上传/保存/整改均0。真实Shadow、真实Live Dry-run和线上Canary NOT RUN。
