# 正常自动整改主流程验收

本轮按最新授权执行：shana1 / Shop7 / PID5097，仅图片动作，不外部找图；Token仅记录。基准任务书a14669b，当前HEAD 20ecfe83e307bbe15e7e298954a7c57d90dcdca6；原有工作区修改保留，无提交或推送，无子Agent。

## 当前可用性

- IMPLEMENTED / FAKE_VERIFIED：完整审核与整改接线、所有现有模型客户端共享用量记录、确认横幅局部裁边、候选质量检查、共享图片去重与SKU引用、保存后回读。
- REAL_VERIFIED（限定本例）：Shop7/PID5097的main[0]和detail[0]顶部卖家横幅裁除，输出800×800；一次上传、一次保存，独立下载字节一致，非图片字段和SKU记录不变。
- 状态PARTIALLY_AUTO_FIXED：20条记录暂缓，不能视为全商品合规；其他图片问题与其他商品尚未逐项真实验收。尚未标为全面PRODUCTION_READY。

## 本轮修改

复用BudgetManager新增RECORD_ONLY；默认CLI与主审核/辅助质量调用仅记账，未知usage/价格保留UNKNOWN/null。显式STRICT/CONTROLLED兼容保留。已确认店铺横幅可以独立于未确定标记整改；800px原图裁边后补方；候选质量检查绑定局部动作范围；写后重新获取的内容若与计划绑定、质量审核通过的候选逐字节一致，直接确认该候选交付。

修复与测试沿用现有模块，无新建业务Runner/模型客户端/第二套账本。真实执行经历三次新Job与一次只读复核；执行版本与验证版本分别归档，详见真实报告。

## 验证

最终完整Fake/Mock回归714项全部通过（603.317秒），0失败、0错误、0跳过；网络拦截尝试0，真实模型调用及线上写入0。测试前后源码哈希一致。详见完整测试日志、状态与源码清单。

compileall与git diff --check通过；原始433项证据与旧SKU验证11个文件哈希全部不变。

本轮41次真实模型请求，网关报告223943 Token，缺失usage为0，美元费用未配置记null；不代表上游核定账单。未执行Token优化。

## 交付证据

- mainflow-5097-real-remediation.md：真实整改与前后图片。
- mainflow-5097-independent-readback.json：独立回读与保护字段检查。
- mainflow-record-only-full-tests.log / tests-status.json / test-source-manifest.json：完整Fake回归与源码绑定。
- mainflow-record-only-evidence-check.json：历史证据复核。
- mainflow-record-only-usage.json：真实调用汇总。
- mainflow-record-only-cumulative.patch：当前项目相对HEAD累计差异，含之前已存在的本项目修改，不是仅本轮增量；不包含邻接项目差异。未暂存新文件亦纳入文本补丁。
- mainflow-record-only-delivery-manifest.json：本轮源码与交付文件哈希。

历史automation-*报告和日志保留不覆盖。线上已完成的保存不重复执行。
