# 8788 Token预算开发与测试报告

本轮本地开发、Fake/Mock回归和离线预检完成；最终PREFLIGHT_BLOCKED。真实模型请求/审核Token/线上写入/自动整改均0。未提交或推送GitHub。

完整回归 **621项通过，0失败、0错误**；unittest耗时见完整日志，含准备总耗时465.312秒。新增34项，原587项全部保留。运行ID：67a6e2dd3c5647ec8b1c0eb7dce42c98。

## 发现与修复

原Runner只在内存中维护预算，缺少权威持久化逐请求记录，无法安全恢复在途请求；调用路径尚未接入可验证的Provider上界。
本机实际是WorkBuddy网关，存在系统提示改写和缺usage估算回填；仅根据DeepSeek/Kimi品牌名或三个整数不能证明计量完整。Provider能力矩阵列出官方文档、适用版本、来源及UNKNOWN缺口。
现在Runner的Fake放行路径使用SQLite权威账本：请求前原子持久化预留、DISPATCHED后调用一次、usage后替换预留，UNKNOWN_COMMITTED保留上界，写盘失败和重启不明状态停止。
增加Provider独立usage校验、重复预留/结算保护、账本版本/Job/逻辑损坏检查、并发1和24/300000固定限制。
STRICT仍禁止未经证明的调用者数字；Fake上界和真实上界分离，没有新增模型客户端，没有触发任何真实模式。

## 变更范围/Git diff

- 修改：scripts/run_8788_real_validation.py（仅预算接线/输出）。
- 新增：scripts/token_budget.py、scripts/config/token.capabilities.v1.json、tests/test_8788_token_budget.py。
- 本轮基线393个受保护源码/数据文件中392个逐字节不变；水印/身份源码、原测试文件均未动。Runner的build_inputs/verify_inputs/request_body/overlay/finish/_http_transport AST完全相同。
- Git分支codex/8788-contract-local-fix-20261114；HEAD保持8399a4eb2c213c43cbebd0350de601556d9eb052；未覆盖main或其他项目改动。
- reports/8788-token-budget.patch是相对本轮开始时工作区的精确补丁；已在独立临时目录通过git apply --check。不能把工作区上轮未提交改动全部归于本轮。
- 修改清单和补丁哈希：8788-token-budget-change-manifest.json。

## 验收覆盖

| 任务书编号 | 验收内容 | 证据 |
|---|---|---|
| 1-6 | 官方上界分项/未知图片/平均值P95/未知模型/过期配置/Provider独立usage | CapabilityTests（10项） |
| 7-18 | 持久化预留/成功结算/不明用量/超界/总量/次数/超时/损坏/写失败/恢复/幂等 | LedgerTests（20项） |
| 19 | 固定串行，两个并发预留只准入一个 | test_two_concurrent_reservations_admit_one |
| 20 | 失败不重试，磁盘失败不能忽略后继续发送 | RunnerBudgetIntegrationTests；原RealValidationTests.test_all_failures_stop_without_retry_preserve_raw_and_usage |
| 21-24 | 预检Provider0、site0、证据433不变 | 新集成预检用例、完整网络拦截、最终哈希复核 |
| 25 | 固定描述排除、六图输入不新增产品字段 | 原FullProductAuditTests排除回归；build_inputs/request_body AST及文件未改 |
| 26-27 | 逐mark聚合、已确认finding与UNKNOWN并存 | 原WatermarkV3Tests.test_confirmed_banner_survives_unknown_small_print等 |
| 28-29 | 身份五维/双模型/0.90门槛 | 原IdentityDimensionTests及WatermarkV3Tests；对应文件哈希未改 |
| 30 | 六图16位置映射不变 | 原RealValidationTests.test_full_sha_six_images_16_positions_no_extra_sku_tasks |

完整34项新增测试名单：8788-token-budget-new-tests.json。

## 实际测试过程

1. 新模块尚不存在时测试RED；首轮Windows SQLite连接未关闭导致清理错误，显式关闭生产与测试连接后26项通过。
2. Runner集成RED证明旧内存预算未落盘，注入账本失败后旧路径仍会执行24次；接入持久化账本后相关测试通过。
3. 追加账本实际值/状态篡改测试先失败，修复逻辑一致性校验；在途total_tokens改为null/PENDING，避免未完成请求被报告为0用量。
4. 冻结源码后运行全量离线套件，621项通过；34项阶段测试通过27.232秒。没有改动旧断言来取得通过。
5. 新预检通过URL/TCP禁止网络的保护运行，捕获网络尝试0，输出exit2/PREFLIGHT_BLOCKED；原433个文件最终全树哈希复核通过。
完整套件主进程URL/TCP拦截，集成子进程仅Fake执行器/本地SQLite/Windows命名管道；这不宣称验证了真实网络、网关或供应商合同。
本轮完整测试及源码前后清单独立保存，不覆盖旧567/587项报告。

## 最终问题逐项回答

- 两模型可证明输入上界：当前WorkBuddy路由均不能；原厂规则没有等价转发证明。
- 图片保证上界：DeepSeek直连有文档1024/张，但本路由不可用；Kimi当前路由无已核实保守上界。详见Provider矩阵。
- 服务端总Token/硬消费限额：当前endpoint/Key均未证明；公开积分说明不能等同300000Token。
- 24次最坏总Token：UNKNOWN/null，不是0、不是均值估算。
- 能否保证24次真实调用≤300000：不能证明，因此STRICT不放行；没有放宽300000。
- 缺失能力：最终请求完整计量、图片与额外开销上界、输出执行保证、usage来源与失败计费核查。
- 预检：PREFLIGHT_BLOCKED是有效安全结果，不把账本Fake通过冒充真实预算证明。

## 交付与Windows复现

- 能力矩阵：8788-token-provider-capability-audit.md；本机来源：8788-token-provider-local-audit.json。
- 设计：8788-token-budget-design.md；最终预检及命令：8788-token-budget-preflight.md。
- Fake账本示例：8788-token-budget-ledger-example.json，明确FAKE，非真实调用账本。
- 全量日志：8788-token-budget-full-tests.log；状态：8788-token-budget-tests-status.json。
- 测试源码绑定：8788-token-budget-test-source-manifest.json；最终证据复核：8788-token-budget-final-verification.json。
- 阶段RED/GREEN、运行脚本、基线副本和过程记录：work/8788-token-budget-fix/。

```powershell
Set-Location 'D:\GitHub\MyE-C-skill\aliexpress-product-image-audit'
$py = '..\ae-img-audit\.venv\Scripts\python.exe'
$env:PYTHONPATH = (Resolve-Path .\scripts).Path
& $py -m unittest discover -s tests -p test_8788_token_budget.py -v
& $py .\work\8788-token-budget-fix\run_offline_tests.py
& $py .\scripts\run_8788_real_validation.py --help
```

本轮未运行真实执行参数、恢复入口或任何模型调用。未验证真实Provider身份/合同、真实Token计量/上界、失败计费查询、真实图片语义或线上SKU现状。
回滚方法见设计文档；保留全部Job/账本/原始证据，无线上变更需回滚。本轮到此停止等待。
