# 独立化最终验收

状态：COMPLETE（本地独立软件交付）。
基准 HEAD：68e168f1a08c6338cb0964dffbd021bb5e484556；证据日期：2026-11-16。

automation 已具有可安装 src 包、CLI/JSON、独立依赖、配置、Prompt、Schema、测试和运行数据。原 V2 的 runner / 客户端 / 计划编译器 / 执行器 / 账本 / 回读器按调用链复用。

迁移前原发现集：931 项，失败 0、错误 0、跳过 0。隔离 wheel 回归：940 项，失败 0、错误 0、跳过 0。原测试发现多重集保留：True；原 Skill 37083 个文件完整性：True；运行依赖静态扫描：True。

四个完整 Fake 场景见 independence-test.md：同照片优先替换零上传、无 twin 边框删除零上传、局部修复一次上传、KEEP 零保存。均使用新 Job、Mock DeepSeek、独立 Fake reader 和真实迁移生产执行链。原始观察与最终策略动作分别归档。

IMPLEMENTED / UNIT_TESTED / FAKE_VERIFIED / LOCAL_CV_VERIFIED 如 feature-parity.md 所列。真实语义模型准确率、真实模型请求、线上读取/上传/保存/部署全部 NOT_RUN；不能标记 PRODUCTION_READY。外部编辑真实服务、训练权重分发和平台单 SKU 多图能力没有新增验证，保留为未来独立事项。

只迁移必要固定夹具：旧验收的六张原图、派生视觉证据、三份输入元数据及一份历史结果对照；重建独立夹具 seal，不改写原 433 文件 seal。未复制旧活动 Job、授权、数据库或缓存。原有固定 V2 图像/人工标签保留来源及 SHA；不得把历史准确率解释为新版真实验收。

软件分发包：dist/mye_c_automation-0.1.0-py3-none-any.whl。使用说明：README.md。完整证据 SHA：evidence-sha256.json。详细原始清单：asset-inventory.json；源→目标及内容变化：migration-provenance.json。

隔离边界明确：wheel 新 venv、原 Skill 和开发源码的 Python 文件读取被阻断；不是 OS 容器。没有改原目录权限。未进行 git add、commit、push。
