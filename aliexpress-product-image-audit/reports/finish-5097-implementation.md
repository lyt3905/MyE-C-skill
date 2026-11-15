# 正常主流程余项完善

范围：Shop7/shana1、PID5097；仅图片及SKU图片引用。单Agent，保留全部既有改动，不提交/推送。仅deepseek-v4.1-flash与mimo-v2.6-pro，门槛0.80，Token只记录，无外部找图。Description及其他非图片字段原值保护。

## 已实现

1. 新增授权装饰拼版整图复核模式，先判断整图构成并检查留存素材，再优先删除；含盒面内容的店铺拼版不再被当作绝对不可删的原始盒照。普通盒照/官方摄影继续保护，非包装判断不会被伪造为false。
2. 多张拼版同时删除时，复核只依赖最终留存的素材，避免待删图片互相充当保留证据。删除后下载留存图片核对字节。
3. 删除动作可解决被删除位置的待确认项，但原始模型UNKNOWN仍保留在审核证据中，不改为PASS。
4. SKU审核行绑定当前快照；已经通过完整审核的现有包装对应无需仅因缺数据库ID就重新暂缓。真正改分派复用现有快照行定位与授权。
5. 图片任务排除未授权的标题/品牌整改；原始检测记录仍保留，报告分开列出范围外发现。
6. 暂缓记录按独立图片内容/问题分组，保留每个业务位置引用，避免把重复记录当成独立问题数。
7. 身份提示词允许引用同商品清晰型号参考图，必须列证据ID；水印提示词澄清包装印刷与摄影版权署名。没有降低0.80门槛或将真实未知值改为成功。

复用auto_deletions、visual_quality、auto_workflow、semantic_remedies、remedy_schema/remedy_binding、plan_compiler、full_product_audit与automatic_report。无新业务Runner/模型客户端/账本。

## 验证进度

新增7项测试，覆盖含盒拼版删除、普通盒照保护、缺留存素材、多个拼版留存、暂缓去重与完整Fake保存/回读。完整Fake案例AUTO_VERIFIED、一次保存、两处整图删除、非图片字段不变。相关26项兼容回归通过。

最终完整Fake/Mock回归729项全部通过（673.797秒），0失败/0错误/0跳过，测试期间源码未变，测试网络拦截尝试0。compileall与git diff --check通过。此前完整回归发现6个同源配置读取兼容错误，已修正为通过既有permits接口读取动作，不跳过或弱化测试；失败日志保留在finish-5097-before-compatibility-*。多拼版补充前的中断记录也单独归档，不算最终通过。

## 真实执行阶段

- audit1：JOB_488c6be3d39f4781ac382b9d967befde，新双模型28次请求，只读；1次未取得有效响应/用量，保留UNKNOWN。
- audit2：JOB_6fe99ff665c64078a1695d636b96dd45，使用澄清后的提示词重新审核；原当前商品未变，只有Prompt/Schema匹配的本轮语义缓存可复用，新Job与账本独立。
- prepare：独立双模型批准main[0]、detail[0]装饰拼版整图删除；计划主图6→5、详情图6→5、SKU图仍2。没有上传或保存。14条暂缓对应5份独立图片内容，不混入两条标题异常或重复的SKU ID缺失问题。
- audit3/apply：JOB_04845d393ca34eb1be3dc4207ca0571c。修复运行统计误封后新建任务，复用同一商品、相同Prompt/Schema的本轮有效语义缓存；两处整图删除已真实保存，1次保存、0上传/翻译/状态/发布，独立API读取及10个保留URL的图片字节核验通过。最终状态PARTIALLY_AUTO_FIXED。

不同阶段的源码分别归档executed-source.zip、prepare-source.zip和后续apply-source.zip。真实请求全文可按账本prompt_sha256核验，原始响应和旧Job不覆盖。

## 当前限制

完整审核已运行，仍有部分文字归属、截断文字、逐标记分歧和2份内容的身份判断未达到共识，不能宣称全部图片合规。即使整图删除成功，也不能把剩余5份图片自动标成CLEAN。

Description固定字段保持原值，里面的历史图片链接不会随images.detail图池删除同步改写。当前工作不构成批量生产就绪验收。

## 本轮补齐的集成问题

保存前发现run_metrics.json在报告中合法更新，却被全量审核清单误当成不可变证据。原任务在写入前停止，未上传/保存。修复为单独冻结full_audit_run_metrics.json，保留所有旧证据，不忽略旧清单的变化；新增测试证明运行统计更新可继续、冻结统计被篡改仍拒绝。最终在新任务audit3完成保存，旧失败记录保留。

## 最终交付

- finish-5097-independent-readback.json：独立线上复验；主图5、详情图池5、SKU图2；标题、价格、重量、状态、品牌、identityJson、Description和完整SKU记录原值原类型不变，其他图池不变。
- finish-5097-remaining-items.md/json：剩余5份内容的当前图片、位置和实际未决原因；14条引用记录未被假标通过。
- finish-5097-prompts.md/json：本轮65次实际请求完整文字，全部与账本哈希核验一致，仅DeepSeek/MiMo。
- finish-5097-usage.json：65次请求，已知网关Token393883；3次用量未知，完整总量记null，不冒充已知；USD未配置，仍仅记录。
- finish-5097-full-tests.log / tests-status.json / test-source-manifest.json：最终729项回归及源码绑定。之前的通过/失败/中断日志单独保留，不混作最终结果。
- finish-5097-cumulative.patch：本项目相对HEAD的累计差异，包含本轮之前已经存在的本项目改动，不包含邻接项目差异。没有暂存、提交或推送。
- finish-5097-delivery-manifest.json：交付与执行源码哈希；执行使用audit3/apply-source.zip。

能力标记：装饰拼版优先删除、当前SKU引用接线、暂缓分组和运行统计衔接为IMPLEMENTED/FAKE_VERIFIED；本商品的两处删除、保留素材及非图片字段保护为REAL_VERIFIED。未宣称所有图片CLEAN或整个系统PRODUCTION_READY。
