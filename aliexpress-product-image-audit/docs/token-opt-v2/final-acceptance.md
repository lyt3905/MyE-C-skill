# 全 Phase 验收与复现

所有 Phase 的离线实现、真实验收和部署验收必须分别记账。单测通过不代表真实模型质量或强制权限隔离通过。

| Phase | 必验项目 | 离线证据 | 外部验收条件 |
|---|---|---|---|
| 0 | 12项v1测试、v1可运行、ZIP冻结、零真实写入 | test_token_opt.py、baseline-v1.zip | 20–30件真实商品基线、人工正负标签、旧双模型原始输出 |
| 1 | 唯一Job、PID/Shop/输入/预算绑定、状态机、锁、恢复 | test_workflow_v2.py及新增绑定测试 | 真实只读商品任务恢复演练 |
| 2 | 候选队列、Schema、失败复核、usage、上下文缓存隔离 | test_ai_judge.py及新增队列测试 | 两真实模型usage和延迟、SKU及标题人工标签 |
| 3 | 下载去重/并发、HEAD 403/404/410、拼版索引、OCR三轮 | test_budget_performance_v2.py；acceptance_v2.py | 原图及v1 OCR输出逐图比对；真实HEAD/下载耗时 |
| 4 | 签名/绑定/过期/重放拒绝、review拒绝、一次save、零status、回读 | test_executor_security.py、test_plan_v2_security.py、test_ipc.py、test_deployment_preflight.py | 独立服务账户部署、管理员隔离审核；获授权后才可验证真实站点 |
| 5 | Shadow、漏检/误报、真实Token、不确定复核 | test_shadow_evaluate.py；shadow_evaluate.py | 同一真实样本集v1/GLM/Kimi/双模型/候选策略及人工标签；未达门槛禁止切换 |

## 一键离线验收

在项目目录运行（不联网、不写站）：

```powershell
$env:PYTHONPATH='scripts'
..\ae-img-audit\.venv\Scripts\python.exe scripts\acceptance_v2.py --output work\acceptance\offline.json
```

JSON保留每条命令退出码及完整测试输出。synthetic仅测注入延迟下载器的并发和去重，不能证明真实v1/v2总耗时、OCR质量、Token或检出率。

## 导入真实样本并生成Shadow报告

准备UTF-8 JSONL，一行一个唯一sample_id，字段严格如下：

```json
{"sample_id":"真实商品PID_图片ID","human_issue":true,"baseline":{"issue":true,"tokens":100,"latency_ms":1000},"candidate":{"issue":true,"tokens":80,"latency_ms":900}}
```

数值必须来自服务端真实usage和实际计时，不能用估算补缺。保留原始响应、人工标注者/日期、商品输入哈希、图片SHA256及v1/v2版本；原始证据与共享报告分开保管，避免带入凭证或隐私。

```powershell
$env:PYTHONPATH='scripts'
..\ae-img-audit\.venv\Scripts\python.exe scripts\shadow_evaluate.py D:\approved-samples\shadow.jsonl --output work\acceptance\real-shadow.json
```

该命令严格校验输入并汇总，不自动批准策略。OCR分级、多图批量和自适应筛选仍须额外真实回归；没有数据则保持原行为。

## 独立部署审查与启动

配置格式、绝对路径及命名管道命令见[executor-ipc.md](../executor-ipc.md)。由管理员先准备独立账户、保护目录、代码、解释器、密钥、凭证和nonce数据库；本项目不会替用户改ACL或创建账户。在服务账户终端执行：

```powershell
$env:PYTHONPATH='scripts'
..\ae-img-audit\.venv\Scripts\python.exe -m executor.deployment_preflight D:\protected\executor.json
..\ae-img-audit\.venv\Scripts\python.exe -m executor.ipc serve D:\protected\executor.json
```

预检退出2必须先处理报告中的具体路径/ACE；不能以配置声明替代。启动也会重复检查。当前共享账户的完整shell环境不能宣称强制隔离。生产写入另外需要可信审批方签发绑定计划的一次性票据。

## 迁移与回滚

先只读运行、留存Job目录和输入哈希，再验证真实Shadow与独立部署。禁止为完成验收擅自生产写站。部署验证与真实质量证据齐全前不启用分级策略。回退时停止新Job及执行器，保留nonce账本、票据使用记录、回读收据、孤立上传清单，切回baseline-v1.zip或已冻结版本；不得重放已用票据。代码回退不等于商品数据回滚；商品恢复必须按原快照重新生成计划并重新授权。

## 尚未满足的最终门槛

缺真实20–30件基线、人工标签与真实模型usage；缺独立账户/ACL与管理员权限隔离实机验收；缺经用户授权的真实保存/回读质量统计。因此最终状态为“离线验证可复现，全部Phase真实验收尚未通过”，不能宣称全部Phase通过。

## 本轮代码补缺及剩余限制

已补SKU/标题显式语义候选、SKU真实图片与SHA绑定、低置信及不匹配转人工复核，并新增语义队列测试。audit_one现已读取policy的标题/品牌/图片阈值；SKU仅在名称明确型号token与高置信OCR型号集合完全矛盾时触发语义候选，不泛扫正常SKU。配置复用及该机器触发均有针对性测试。

Token限额仅在配置total_tokens时开启；请求前预留为保守估算，图像Token并无可证明的严格上界。结算保留实际用量，不能将估算混入actual。默认未配置Token限额不能声称默认硬Token预算已完成。workflow现已将非null token_limit接入total_tokens预算资源，并拒绝非法值；usage缺失后在事务内拒绝后续受限Token请求。Job哈希文件校验用于防误改，不是抵抗同账户任意文件修改的安全边界。
