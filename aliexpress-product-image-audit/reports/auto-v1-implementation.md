# Auto v1 实施进度（持续更新）

需求源：C:/Users/shana/Downloads/aliexpress-auto-audit-remediation-codex-plan.md。保持 Phase 0–9 完整范围，尚未验收完成，禁止按完整生产版本发布。

## 当前已完成的开发与证据

- 保留原工作区未提交内容；未用 ZIP 覆盖。Git HEAD b84cc545ff94057bba5bafbebc3a090d3d32abe1。
- 缺 images/main/detail/必需 SKU 池误通过：新增回归先失败后通过。
- watermark 候选稳定业务 ID、pool/index/源 URL/源 SHA；真实 transport current_shop 只读适配。
- 原始 REMOVE_CANDIDATE 未选动作不再结案；上传替换同步完整 URL 的图片池/SKU/描述引用。
- Dry-run 使用同一模拟器，上传用 UPLOAD_TOKEN 展示差异，零上传/零保存。
- 独立本地 automation-policy/v1：店铺/PID/动作白名单、预算、安全硬约束和配置哈希。未创建或启用用户本地生产配置。
- RemedyCandidate 质量契约、逐项 AUTO_SAFE/DEFERRED/BLOCKED_FATAL；v3 自动计划保留 v2 兼容读取。
- 复用 imgpool pHash 与 clean_band 裁切；独立解码/尺寸/SHA、三轮 OCR、残差、模板与双模型复检适配器。缺模型/复检不能通过。
- SKU 包装/型号分派算法；标题 SOP 词表、前缀、Megatank、型号、Upgrade Kit、长度压缩；两者编译接口已实现，但尚未全部接入标准 Workflow 候选规划。
- account 级串行自动执行、本地授权、一次保存日志、写前漂移检查、写后字节读取与质量复检。
- 无实际变化零保存；标题变化后独立翻译，失败返回 TRANSLATION_PENDING，不再次 save。
- 已通过的标准 Workflow + Fake 闭环：孪生替换、裁切上传、部分成功与详情异常保留。
- CLI 已接入 audit/dry_run/auto_apply 和 report；尚未对生产运行这些命令。

## 下一步（仍为原任务要求，不能省略）

1. Phase 0/1 补齐 SOP 覆盖追踪；description 独立图及 ai/scene 全池；semantic 图片 ID 全面统一；畸形数据拒绝；严格模型缓存输入绑定。
2. Phase 2/3 强化编译器候选质量记录/SHA绑定、默认 inspector 在缺环境下的异常隔离、本地图池标准入口；简单背景试擦与主体/官方保护回归。
3. Phase 4/5 将已实现 SKU/title 模块接入 auto_workflow.prepare；真实双模型来源/回译一致性；完成对应两条 Workflow→Fake Executor 闭环。品牌真实字段映射不明确必须 DEFERRED。
4. Phase 6 自动执行保存/翻译预算接线、同 PID 跨 Job 幂等、恢复/不可盲目重试、配置修改再检查、account 锁恢复、Dry-run 店铺身份严格检查。
5. Phase 7 结果持久化、自动 resume、标题/分派读后内容复检、TRANSLATION_PENDING 传递、完整指标报告。
6. Phase 8 --batch/--pending、1/3/10 件 Fake、熔断和有界并发、跨 Job 缓存和图像预留完整回滚。
7. Phase 9 E01–E35 独立矩阵、全回归、独立审查、10 份最终报告、完整 Schema、部署/回滚文档、代码变更包。不得把当前绿测试替代这些验收。

## 验证记录

- 初次系统 Python 依赖不完整，失败日志保留；后改用相邻 ae-img-audit/.venv，Windows Python 3.12。
- auto-v1-windows-baseline.log：125 项，4 处旧夹具与缺池阻断要求冲突。
- auto-v1-phase3-regression.log：151 项通过。
- auto-v1-phase6-regression.log：177 项通过。
- 最新完整结果见 auto-v1-current-regression.log。测试数含已有模块被测试导入后重复发现的项目，不能等同独立场景数。
- 未连接生产商品试写，未执行真实模型/真实站点验收。

## 本轮规则裁决

- 用户明确要求在当前工作区继续，保留已有改动；不迁移到丢失未跟踪模块的空白 worktree。
- 补齐旧安全测试的必需图片池，保留授权/快照/IPC 断言；原本期望空计划 save=1 的断言按新需求改为 save=0。零保存预算测试改为真实 titleEn 变更，继续证明预算拦截。
- audit/dry_run 不提供写能力；auto_apply 才读取独立本地授权。未启用外网找图/删除/擦除生产动作。

## 本次续行追加

- 四条标准 Workflow→Fake Writer 闭环均已具备：孪生、裁切、SKU 分派、英文标题及独立翻译。参见 test_auto_workflow.py、test_auto_workflow_more.py、test_auto_semantic_workflow.py。
- 已实现 batch_scheduler.py 及 --batch/--pending CLI 接线；1/3/10 件调度与 APPLY_UNKNOWN 熔断的单元测试通过，但尚未完成完整 Workflow 10 件批次验收。
- 完整 Windows 回归最近一次 185 项通过（随后小改动仍需重新运行）；日志 auto-v1-current-regression.log。
- 上文“SKU/title 尚未接入”的旧进度已被本节取代；两条都已接入。Phase 9 完整验收仍未完成，目标仍 active。

## 后续必须优先审查的实际代码问题

1. run_automatic 的自动 terminal/resume、幂等持久结果和 APPLY_UNKNOWN 只读恢复尚不完整；account 锁当前位于 root，跨 root 不共享。
2. LocalExecutor 自动分支尚未传入持久 BudgetManager（site_save/translate）；policy 文件运行中变化也应重新读取。
3. SKU/title 新链还需翻译失败、分派不确定、字段类型、品牌映射与回读漂移的更多端到端负例。
4. 简单背景试擦尚未实现；本地图池 planner 有能力但主流程尚未读取显式来源索引。
5. 机器全池 description/ai/scene 与语义 stable image ID 仍未完成；旧 check.py CLI 未全面验收。
6. 编译器需要更强的 candidate_quality.json 与源文件 SHA 校验和动作范围约束；不应只信输入 checks。
7. 质量复检异常按项隔离、AI额外图片缓存/预算、完整指标报告、35场景矩阵及独立审查仍待完成。
8. 示例配置 enabled=true 只存在示例中；未创建 local/automation.v1.json，没有启用生产。

## 第二次续行追加：恢复、证据与审查修复

- 本地授权从文件加载后，每次授权与实际上传/保存前复核文件哈希；运行中禁用或修改配置立即失效。
- 自动写入预算已接入 LocalExecutor 的持久 auto_write_budget.sqlite，保存预算在上传前预留，上传/翻译各自扣账。
- 完成结果持久化 automatic_result.json；已完成 Job 不重新审核/写入；APPLY_UNKNOWN 不重开执行。
- expected_after.json 在 save 前持久化；新增 recover-readback --job --site-config 只读入口，区分 MATCHED/NOT_OBSERVED/DRIFT，始终 retry_save_allowed=false。MATCHED 只证明结构写入，不冒充图片内容已验收。
- 全池审核覆盖 descriptionJson 独立图片、images.ai、images.scene；SKU/identity 模型输入统一稳定业务 ID。
- 简单背景试擦已接入 planner 与双模型几何提案：仅主体/包装/官方要素包围框外、面积≤2%的小区域；记录掩膜/SHA，逐像素验证掩膜外不变，独立OCR/残差/视觉复检失败即弃用。生产 ERASE_LOCAL 仍默认关闭。
- 本地图池通过显式 local_pool_index 接线。索引 schema=official-image-pool/v1，官方来源/型号/包装类型/完整来源URL/文件SHA缺一不可；目录名不算来源证明。
- 中期独立审查发现并修复：共享URL的DEFERRED引用被连带修改；品牌单字段回读遗漏；标题授权越权URL映射；候选伪造checks/SHA可编译；预演缺Shop核验；SKU读后忽略型号/字节SHA。
- 孪生替换现额外要求 model_match 和 packaging_match 明确通过，pHash绝不单独授予执行。
- 编译器通过 remedy_binding 对照 audit_raw 实际源文件、candidate_quality 独立记录和 semantic_validation；计划绑定相关证据文件SHA。窄编译器单元测试夹具已补充Fake质量记录，标准Workflow闭环仍从真实候选生成启动。

剩余优先项（本节取代前文已完成项）：跨root账号锁/同PID跨Job幂等与锁恢复；恢复后内容复检/独立翻译重试；完整试擦与本地池标准Workflow E2E；品牌生成与站点字段映射；删除白名单动作；read-only在本地自动配置disabled时的预案生成；质量异常逐项隔离；所有预算/缓存边界；完整10件Workflow批次；check.py CLI；E01–E35全矩阵、完整Schema与10份最终报告、最终独立验收与变更包。

## 第三次续行追加

- audit/dry_run在enabled=false的本地自动配置下仍可只读审核；写入授权仍强制enabled=true。
- 账号锁改为跨root的内核文件锁；同账号串行，不用删除持久锁文件释放权限。
- ExecutionLedger持久记录账号/Shop/PID/源状态/动作指纹；未知写入阻止新Job，同一源状态/操作不重放。
- 标题/SKU可选验证器异常按项DEFERRED；不清空异常、不冒充CLEAN。
- 模型图片/Token/请求预算采用单次事务统一预留，任一失败全回滚；比较图SHA变化拒绝缓存CLEAN。
- check.py新增 --job-dir 离线结构+证据+内容结果验收；只读客户端补齐download适配。
- 1/3/10件完整Workflow Fake批次均通过，每件upload=1/save=1/readback，非仅调度回调测试。
- Site.save把identityJson dict序列化为JSON字符串；状态哈希按其语义对象计算，避免API表示差异误报漂移。已有旧计划应重新审核/生成哈希，不能盲目复用。
- 裁切改用等比缩放+白底补方；辅助池在v3计划内完整保留，且不随主图URL重映射被误改。AI/scene仅审计，不直接作为自动孪生来源。
- 新增baseline、当前接口契约、SOP覆盖矩阵和剩余清单。它们记录当前实现，不是替代开发的新方案。

## 第四次续行追加

- retry-translation：一次持久化的独立翻译重试（初次+重试合计最多2次），不上传/不save；字段漂移拒绝重试。
- verify-saved：对已保存Job重新读取并复检内容，成功后更新报告/状态/ExecutionLedger，图片和商品不重复写入。读回允许专用API改变titleTranslationZh，但仍需独立语义检查。
- 独立质量证据ID绑定源SHA、候选SHA与业务上下文；回读复检不覆盖保存前的质量证据。
- 增加从 audit_one.audit 实际预审开始的Fake下载/OCR测试：背景试擦和官方本地图池全链通过，带水印的官方池候选被拒绝；未手工构造ai_queue/plan/audit_flags。
- 官方池来源SHA与目标原图SHA分开绑定，修复首次完整闭环暴露的错误。
- 三份JSON Schema已入库：automation.v1、remedy-candidate.v1、plan.v3；在实际Workflow产物上验证。JSON Schema负责结构，Python验证器继续负责动作范围/状态/源证据等跨字段语义。未知Policy字段拒绝。
- 自动品牌整改只支持明确、已存在的整数brandId字段及已知SOP code；出现brand别名或类型/映射不明继续DEFERRED。Fake标准Workflow品牌单字段闭环通过。
- 上传按SHA去重，预演和实际上传使用同一去重占位；v3实际上传URL先回读字节SHA，通过后才save。失败也持久化上传回执。
- Site.upload按真实图片格式发送MIME，修复PNG被声明为JPEG的问题。
- 增加requirements-auto.txt/requirements-dev.txt及Windows一键完整测试 scripts/run_auto_tests.ps1；最终运行日志仍保存统一路径。

仍需继续：DELETE_REDUNDANT完整白名单；E01–E35逐项最终矩阵；干净商品只读验收/模板适用性和CLI异常分支；全部自动阶段指标汇总；受控回滚演练/变更包；最终独立审查。真实站点/模型/生产读写仍未验证。

## 最终复审续行

新增生成整改图供SKU分派、依赖授权和最终URL回读；Fake完整流程通过。新增BOX_NORMALIZE显式授权（示例默认false）、原图盒照/型号/SHA观察、LANCZOS白底补边轻锐化、独立质量绑定，Fake上传1保存1回读通过。E07实际audit_one入口双模型分歧场景通过：详情保留，主图独立整改保存。E23空URL立即失败并记录回执。打包器补齐ps1/SOP/依赖并排除缓存。

复审Important：生成图观察RuntimeError阻断独立动作，已RED复现并修复为该候选降级；5项生成SKU测试通过。此前完整回归280次/42.118秒通过；最新异常隔离修改仍须再次全回归。

## 最终审查第二批修复

内容复检失败优先于翻译待重试，主流程和恢复验证均修正；混合失败批次测试断言第二件不启动。新增upload_rate.py全局上传SQLite互斥与完成后0.5秒间隔，跨账号共享；去重上传不占新时隙，异常也持久记录间隔，数据库异常不执行上传。Fake时钟验证通过。README补齐安装、配置、入口、恢复、节流说明。

AUTO_CONDITIONAL已接入图片候选独立质量检查，条件未完成时不进入计划；动作级校验与本地授权通过后才记录AUTO_SAFE，失败DEFERRED。过程在conditional_decisions.json及report_data中保留，纳入计划evidence_refs。新增条件失败/成功及完整裁切流程断言通过。
