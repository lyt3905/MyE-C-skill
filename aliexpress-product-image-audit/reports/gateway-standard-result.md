# 新网关标准接入：验收结果（2026-11-13）

标准CLI已支持 --model-config，无需改源码或用临时单模型脚本。配置包含网关、恰好两个不同模型、输出额度、重试和超时；复制绑定到Job，主审核与独立质量检查共用同一份设置，恢复不重读外部配置。默认模式兼容，既有账号/账本架构、SOP与业务范围保持。

最终完整487项/255.927秒/OK，进程退出0，compileall退出0。新增配置验证9项、CLI等8项、策略状态一致性3项、未知用量边界2项，共22项；首轮相关30项、策略修复相关19项、最后用量修复相关33项均通过。原始RED/GREEN日志、一次测试数据缺task_type的失败及修正均保留。源码清单238文件，原233及中间237/238文件清单均留备份。

本目标按原文允许明确暂缓的实际审核/整改预览完成验收；要求成功执行的测试对象是Fake/Mock。真实可执行方案的final_check/live_dry_run通过仍未证明，不能将下面的DEFERRED称为整改成功或批量已就绪。逐项验收见gateway-standard-goal-audit.json。

## 三件商品真实只读运行

标准命令为run --batch 5099,5098,5097 --shop 7 --mode dry_run，并显式传入model.readonly.json、policy.readonly.json及Shop7筛查模板。网关3425，DeepSeek/Kimi两模型，输出上限8192、retries=0、timeout=90；每件45请求/300000Token上限，写入策略disabled。总运行714.309秒，退出0。

| 商品 | 主图/详情/SKU | 下载成功 | 结果 | 实际请求 | 已报Token小计 | 未知usage请求 |
|---|---|---|---|---|---|---|
| 5097 | 6/6/1 | 13 | DEFERRED | 15 | 43452 | 1 |
| 5098 | 7/6/1 | 14 | DEFERRED | 8 | 29692 | 1 |
| 5099 | 7/6/1 | 14 | DEFERRED | 22 | 45005 | 1 |

合计41次图片出现、20个不同SHA，41/41下载成功。45次模型请求与预算/统一报告逐Job核对一致，实报Token小计118149；另3次独立质量调用超时，usage未知，因此总消耗UNKNOWN。3次超时均按90秒配置终止客户端等待；不能保证上游推理已停止，也不将未知费用记0。没有自动循环重试或重置预算。

三件均在候选规划后明确DEFERRED，无AUTO_SAFE动作；没有进入live_dry_run或final_check阶段，不称DRY_RUN_PASSED、整改成功或真实写后验证。本轮交付的是每件商品可审查的整改预览结果（当前无已验证安全方案）及暂缓原因。新配置下真实成功写入、真实可执行方案的最后预演均未在本轮证明。

补充4083实际预演（独立新PID、无写入）共24请求/80400实报Token，全部usage已知，结果仍DEFERRED，独立GET确认源状态未变。本目标实际模型调用总计69次，实报小计198549 Token，另3次超时usage未知，总消耗仍UNKNOWN；不包括Fake、离线复算或目标开始前的探测。

## 逐图与规则边界

逐图主队列结果为11 REVIEW、6 CLEAN、1 HIT、23 NOT_QUEUED。CLEAN仅指该次水印任务输出，不代表商品整体合规；NOT_QUEUED仅表示未触发机器送审条件，未伪称模型通过。所有41项均绑定源URL、索引、源SHA、模型事件或明确原因；独立质量事件单列。

R01/R02/R03这三张SKU原厂图在标准主水印队列中未入队；R04/R05/R06均为REVIEW。R04当前两个返回都识别店铺横幅，但置信度0.92/0.85，未达到双模型均>=0.90；此前独立Shadow的HIT不覆盖本次结果。R06有一个低置信marketing_text倾向（0.62），与人工原厂标签冲突，融合仍REVIEW，不记为一次实际误删或已放行错误。

R04人工整删标签继续保留且仅绑定原PID5097/main[0]。同SHA的其它目标仅关联水印真值，不自动继承删除动作。既有盒照/包装内容保护及此前独立整删拒绝不放宽；当前作为SOP冲突异常分支处理，未改假is_box、未删除。低置信/abstain、不同归属、服务失败、预算保护、动作未授权、主图7张和缺SKU ID分别保留，详情见逐图及deferred记录。

## 独立验证与执行边界

任务结束后重新登录已有站点只读客户端，逐件独立GET，前后核对账号与Shop7。三件完整受保护状态哈希均匹配，价格输入、标题、Description、SKU及图片引用未变。没有执行/保存/上传/执行预留产物；标准dry_run代码只实例化ReadOnlySiteClient并在执行前返回，策略disabled。原始未测量执行计数保留null，不用null冒充实测0。

Fake标准CLI在新profile下已验证安全高清替换→保存→回读AUTO_VERIFIED；HTTP失败、双模型冲突和包装保护均0上传/0保存。另有真实协议Fake检查两个模型的地址、输出额度、超时与预算预留一致，配置不同缓存隔离、Job防篡改及主/质量两阶段一致。Fake通过不增加真实整改样本数。

## 补充边界修复

验收补充修复两项：中文促销海报被汇总CLEAN而既有策略要求复核；畸形网关响应未正确封闭UNKNOWN预算。均先RED后GREEN且未放宽任何动作。30对已有真实返回离线复算仅4083一项CLEAN→REVIEW，策略处置不变。完整说明见gateway-standard-policy-and-usage-fixes.md。

## 未验证项目

本轮3件都是之前只读样本的标准入口复跑，不扩大独立样本/准确率分母。标签仍47个不同内容、39二元真值（13正/26负）、8仅动作标签、11整删确认；SKU正例仍0。每类动作30个确认样本/98%门槛不足，批量关闭。接口几何/质量任务仍有超时，不能称稳定性全部解决；23项没有主水印模型结果；新网关真实安全动作成功预演/真实写后成功未证明；R04盒照规则冲突未解除；完整生产故障恢复和远端回滚未诱发验收。本目标只授权Fake执行，未以补样本为由进行生产试写。

## 交付文件

- gateway-standard-windows.md：标准运行命令、模型配置、回退与异常处理。
- gateway-standard-live-summary.json / gateway-standard-per-image.json / gateway-standard-readback.json：三件结果、逐图证据和独立回读。
- gateway-standard-label-comparison.json：人工真值、低置信错误倾向、服务错误及SOP边界。
- gateway-standard-final-full.log / -status.json：最终487项终态；gateway-standard-full为首轮482项，gateway-policy-alignment-full为中间485项；三轮及RED/GREEN记录均保留。
- gateway-standard-source-changes.json / v1.3-current-source-manifest.json：本轮源码清单及SHA。
- scripts/config/model.gateway3425.example.json：无密钥的模型配置示例；本轮实际8192配置与disabled执行策略在work/gateway-standard-20261113。
