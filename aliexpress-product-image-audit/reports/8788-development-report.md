# 8788审核契约修复开发报告

本轮本地诊断、代码修复与Fake/Mock验收完成。未重新运行原真实审核/续跑，未消耗新审核模型Token，未写入线上商品，未提交或推送GitHub。
最终完整回归：**567项通过，359.192秒，0失败、0错误**；新增33项测试。最终测试运行ID：`816f2a4ceffc4eb3918abd7cc023336f`。
本轮不宣称新Prompt已通过真实8788验收，也不把历史商品审核改成COMPLETE。

## 证据与源码基线

- 基线HEAD：8399a4eb2c213c43cbebd0350de601556d9eb052；本地分支codex/8788-contract-local-fix-20261114。开始时审核项目无未提交修改，其他项目已有改动未触碰。
- 7个重点基线文件的LF文本与原审核清单已核实；历史原始字节SHA、Git blob SHA与本轮修复后本地SHA分列在8788-source-version-audit.md/JSON。没有用main覆盖工作区。
- 原Job及续跑目录433个文件全树哈希不变；原有9项parent_bindings通过；已确认finding规则/位置保留，历史数值未改。
- 原阶段和续跑的总Token仍UNKNOWN，已知小计273,807。本轮新增真实审核模型请求/Token/线上写入均0，旧28次额度未复用。
- 最终Fake测试开始/结束的源码哈希一致，当前文件也仍匹配。8788-test-source-manifest.json记录逐文件原始/LF哈希、Python版本及已加载本项目模块路径/文件哈希；这是本地测试溯源，不追溯补证旧模型进程。

## 修复前后对照

| 项目 | 修复前 | 修复后 |
|---|---|---|
| 水印契约 | root Prompt/Schema与marks消费者错位 | watermark/v3统一逐mark、原图尺寸、覆盖/无标记声明、区域、弃权与证据绑定 |
| 空marks | 一律UNKNOWN或缺少明确来源 | 仅双模型达到原门槛、完整覆盖且显式无标记才PASS |
| 局部确认 | 整图UNKNOWN难以解释局部事实 | coverage/review/finding/unresolved分开，PARTIAL保留确认finding |
| 区域比较 | 没有明确逐区域一致性契约 | 配置化IoU=0.5；测试边界、乱序、未配对与歧义区域，类别冲突不跨区域传播 |
| 历史兼容 | root有效不代表marks完整 | 只作legacy观察，coverage不完整；保留真实局部低分和root分类差异，不补造bbox或覆盖声明 |
| 缓存 | 格式变化可能混用 | Prompt+显式Schema版本进入key，读取严格验证，legacy结果不写入新格式缓存 |
| 身份 | 型号、颜色、类型等被合成一个UNKNOWN | 主体、图片类型、型号、颜色、包装五维独立观察与原因；root门槛仍控制整图结论 |
| 旧置信度 | 没有每维独立分数 | 根级分数保留为ROOT_ONLY，不把它分摊为每维置信度；缺失维度分数保持UNKNOWN |
| 报告 | 原因泛化 | 16业务位置、141条模型/字段/区域原因，包含旧v1首个触发分支与新契约缺项的区别 |
| 同SHA | 模型队列已去重 | 聚合也每SHA只算一次，映射所有位置；SKU行及图池索引同时保留 |
| 调用前置 | 缺少原尺寸也可能进入模型阶段 | 无可信原图尺寸在预算/请求前SOURCE_UNVERIFIED |

0.90与双模型要求均未降低。新区域类别冲突（包括不同REMOVE子类）保持UNKNOWN，不沿用旧root子类合并作为新区域一致性。独立候选质量、SKU修复和写入授权保护继续保留。

## 真实历史结果的本地诊断结论

契约错位属实，但不能把全部UNKNOWN归因于缺少marks。横幅图实际已有marks，旧v1还因营销类别待定和局部低置信返回UNKNOWN；其他图有root弃权、0.82/0.84/0.86/0.88等低分以及BOX/MIXED差异。
新诊断逐条记录原始值与字段路径；旧结果缺少新覆盖声明、像素区域或维度置信度时，明确标为格式/信息不足，不伪装新模型输出。摄影署名、原厂印刷和包装保护；横幅已知NON_COMPLIANT保留，完整审核仍未完成。
同名JSON保存每个位置的宽高、pool/index、每mark/legacy观察、确认finding、未解决项、五维身份和SKU包装状态。可选文件不存在的位置完整列于矩阵，不猜测内容。

## 验收覆盖

| 指令用例 | 检查点 | 测试 |
|---|---|---|
| 1-3 | 横幅确认与其他小字UNKNOWN并存；finding不会被覆盖 | WatermarkV3Tests.test_confirmed_banner_survives_unknown_small_print |
| 4-7 | 摄影、社交署名、原厂标识与商品印刷保护 | WatermarkV3Tests.test_each_protected_class_passes_without_removal |
| 8-9 | 完整无标记可PASS；缺少覆盖/无标记证据不可PASS | WatermarkV3Tests.test_no_marks_requires_both_explicit_exhaustive_confirmations |
| 10 | 单模型弃权时保留有效局部观察 | WatermarkV3Tests.test_root_abstention_preserves_other_model_local_observation |
| 11 | 同区域类别冲突只影响对应mark | WatermarkV3Tests.test_same_region_class_conflict_does_not_erase_other_region |
| 12 | 数组乱序和不同区域不错误合并 | WatermarkV3Tests.test_region_matching_is_independent_of_array_order / test_unmatched_regions_are_not_combined |
| 13 | 缺失、越界、非法坐标、外来evidence ID拒绝；无原尺寸调用前阻断 | WatermarkV3Tests.test_schema_rejects_invalid_boxes_and_unbound_evidence / test_missing_original_dimensions_blocks_before_provider_call |
| 14 | 旧root保留finding但不伪装成完整覆盖 | WatermarkV3Tests.test_legacy_roots_preserve_finding_but_not_coverage |
| 15 | Prompt/Schema版本参与缓存键，旧结果不能占用新格式缓存 | WatermarkV3Tests.test_contract_version_changes_cache_key / test_old_root_cache_cannot_satisfy_new_contract |
| 16 | 型号不可见保持UNKNOWN | IdentityDimensionTests.test_model_not_visible_is_unknown_not_mismatch_or_match |
| 17 | BOX/MIXED冲突与主体观察分开 | IdentityDimensionTests.test_box_mixed_conflict_is_separate_from_subject |
| 18 | 精确SHA语义聚合一次，映射所有位置；SKU引用独立 | IdentityDimensionTests.test_sha_analysis_is_reused_for_each_business_position / FullProductAuditTests.test_only_exact_sha_deduplicates_inference_not_business_positions |
| 19 | 固定描述不进入审核；本轮未新增描述输入 | 既有 FullProductAuditTests.test_source_text_annotations_reach_models_without_description_or_prices 等排除回归；离线诊断不解析商品原始快照 |
| 20-21 | 未授权真实模型/线上操作为0 | OfflineDiagnosticsTests.test_report_is_offline_preserves_evidence_and_explains_missing_fields；完整套件URL/TCP拦截及Fake子进程 |

## 测试过程

- 首批契约测试先失败，再实现并运行至通过；绑定、身份root分歧、旧分数范围、原因隔离、SHA复用等追加用例均保留RED/GREEN日志。
- 相关模块阶段113项通过，20.783秒；最终完整套件覆盖本轮所有新测试及原功能回归。
- 首次完整套件561项出现两个子进程导入错误：自定义启动器未传PYTHONPATH。修复启动器环境后，阶段566项通过；最后补齐元数据/原因回归与冻结源码证明，最终567项通过。中间日志只作过程记录，不冒称最终源码验收。
- 567项耗时359.192秒；进程状态计时359.640秒含准备。完整日志/状态：8788-full-tests.log / 8788-full-tests-status.json。
- 网络拦截施加于测试主进程；本地IPC/上传节流子进程仅使用Fake执行器、临时SQLite及Windows命名管道。拦截到的外网尝试0；离线诊断单独验证urlopen、Judge请求和站点客户端构造均为0。
- 全部历史文件433项最终哈希复核通过，旧finding逐位置保留，证明见8788-final-verification.json。

## 修改文件

- README.md
- scripts/ai_judge/cache.py
- scripts/ai_judge/client.py
- scripts/ai_judge/identity_contract.py
- scripts/ai_judge/product_identity.py
- scripts/ai_judge/schemas.py
- scripts/ai_judge/watermark.py
- scripts/ai_judge/watermark_contract.py
- scripts/audit_diagnostics_v2.py
- scripts/config/watermark.matching.v3.json
- scripts/full_audit_recovery.py
- scripts/full_product_audit.py
- scripts/policy_engine.py
- tests/test_8788_contract.py
- tests/test_8788_offline_diagnostics.py
- tests/test_ai_judge.py
- tests/test_ai_judge_json_content.py
- tests/test_ai_judge_usage_settlement.py
- tests/test_auto_comparison_cache.py
- tests/test_full_product_audit.py
- tests/test_model_gateway_cli.py
- tests/test_model_policy_alignment.py
- tests/test_round2_budget.py
- tests/test_v13_gateway_diagnostics.py
- tests/test_v13_image_observations.py
- tests/test_v13_store_policy_consensus.py
- tests/test_v13_store_policy_consensus_cli.py
- tests/test_watermark_prompt_contract.py
- tests/watermark_fixtures.py

完整可应用补丁：8788-code-changes.patch，UTF-8/LF；已在独立临时Git索引上针对基线HEAD做git apply --cached --check验证，不改实际索引。报告及原始运行数据不混入代码补丁。

## 交付索引

- [源码版本核对](8788-source-version-audit.md)及同名JSON。
- [UNKNOWN根因](8788-unknown-root-cause.md)、[原因矩阵JSON](8788-unknown-reason-matrix.json)。
- [离线逐图诊断](8788-audit-diagnostics-v2.md)及同名JSON。
- [完整测试日志](8788-full-tests.log)、[测试状态](8788-full-tests-status.json)、[测试源码绑定](8788-test-source-manifest.json)。
- [新增测试清单](8788-new-tests.json)、[改动清单](8788-changed-files.json)、[代码补丁](8788-code-changes.patch)。
- [最终证据复核](8788-final-verification.json)、[离线调用拦截核对](8788-offline-guard.json)。
- 过程RED/GREEN及前两次完整套件日志位于work/8788-contract-fix-20261114，未覆盖原Job。

## Windows本地验收命令

```powershell
Set-Location 'D:\GitHub\MyE-C-skill\aliexpress-product-image-audit'
$py = '..\ae-img-audit\.venv\Scripts\python.exe'
$env:PYTHONPATH = (Resolve-Path .\scripts).Path
& $py -m unittest discover -s tests -v
# 带网络拦截和源码前后绑定的本次验收启动器：
& $py .\work\8788-contract-fix-20261114\run_offline_tests.py
# 只读既有文件的诊断，不构造站点或模型客户端：
& $py .\scripts\audit_diagnostics_v2.py --job-dir .\work\full-product-audit-20261114\jobs\JOB_93099438cf014a689846bc05469759ad --output .\reports --declared-model DW-ES09T
```

不得运行原full_audit_recovery.py、重启旧Job或复用旧授权。以上命令均不启动真实审核。

## 未验证及后续预算估算

- 新Prompt/Schema的真实8788输出质量、穷尽覆盖能力、bbox准确度和置信度校准尚未验证；本轮只有Fake/Mock验收。
- IoU匹配阈值完成Fake几何/歧义边界测试，没有真实标注集区域匹配验收；聚合finding本身不提供写入授权。
- 旧root数据无法补出未记录的覆盖、区域与逐维置信度；当前真实商品不因此变成审核完成或整改完成。
- 历史源文件快照可核对，旧进程逐模块/依赖溯源仍不完整；不补造证明。旧未知用量仍UNKNOWN。
- 若另获授权重新验证6份不同图片，新水印6×2=12次、身份6×2=12次，共24次。SKU两行若快照/规格变化再预留4次，共28次；使用新授权和新可追溯运行，不重启旧续跑。
- 按上一轮158091/28的已知均值，24次粗略基线约135507 Token；新穷尽结构和推理可能增加，粗估15万～30万，规划预留30万～50万，仅估算，不是授权或实际用量。详见8788-next-run-estimate.json。
- 涉及任何真实模型调用或线上操作时必须停止等待新的明确授权；本轮到此仅交付本地修复。
