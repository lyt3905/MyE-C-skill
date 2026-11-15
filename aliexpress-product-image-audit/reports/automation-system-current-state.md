证据日期：2026-11-14；源码基线：20ecfe83e307bbe15e7e298954a7c57d90dcdca6；对照 a14669ba76aae5dbf72b00afe83b8028dc3cba97。
本轮范围：单Agent，本地开发/Fake/Mock；无真实模型或站点操作。最终本地验收见 automation-final-acceptance.md；Fake与真实证据严格分开。

# 当前系统审计

初始分支 codex/8788-contract-local-fix-20261114；HEAD 20ecfe8。本项目与 a14669b tree 相同；HEAD身份不同，不reset、不覆盖。仓库外部已有 profit-ledger-registration 三文件修改及 monitor-ops、zip、截图等未跟踪内容均保留；初始状态和未提交diff封存 work/automation-system-20261114/。

原有 full-audit 生成完整 inventory/queue/judgements/report/coverage/manifest，但 run_automatic 原先走 workflow_v2_pipeline 的机器候选队列。两者未形成完整审核到计划的证据链，不能把候选队列的CLEAN等同全商品合规。

JudgeClient 原先可4并发、2重试，BudgetManager的Token预留是估算，token_budget STRICT仅用于历史六图验收Runner。VisualQualityInspector另建JudgeClient但复用Job budget.sqlite；必须在公共预算层统一范围和用量。

Python复用相邻 ae-img-audit/.venv（Python3.12），未重建、未安装依赖。系统GPU sitecustomize已存在，测试日志保留其启动信息。

项目配置新建前不存在；gpt-6.1-sol在当前桌面模型缓存目录可见。写入项目配置不证明当前会话的模型/权限已切换；本会话权限由宿主控制，未修改全局配置。官方配置参考：https://learn.chatgpt.com/docs/config-file/config-reference 。

有效范围：仅main/detail/sku与SKU引用；Description不解析不下载不入模型，快照原值用于受保护字段漂移比较。images.ai/scene保留。

历史证据边界：5097正式28请求+补充2请求=30，网关177351Token；水印/身份UNKNOWN、模板缺失，SKU最新补丁只离线验证。5093仅main[3]曾1上传1保存成功，17项暂缓；不代表当前集成版本真实通过。
