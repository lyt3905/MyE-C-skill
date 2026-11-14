# 验收中发现的两项边界缺陷

## 促销海报汇总状态与现有策略不一致

真实4083预演中，两模型均返回chinese_promotion_poster、置信度0.90，旧JudgeClient却汇总为CLEAN。既有policy.v2.json原本要求NEEDS_REVIEW，后续规划已拒绝动作，因此没有误删，但审核汇总有误导风险。marketing_text也存在旧汇总HIT而策略要求NEEDS_REVIEW的不一致。

先增加回归：2个测试出现3个失败断言；随后加入第三个全策略类别覆盖测试。修复仅令水印汇总读取原KEEP/REMOVE集合：现有保留类为CLEAN，现有移除候选类为HIT，其余为REVIEW。低于0.90、弃权、模型分歧和不同具体店铺的既有保护均保留；非水印任务逻辑保持。没有改策略文件、扩大REMOVE类别或新增删除许可。

相关19项/8.648秒通过。30对原始真实返回以零预算缓存离线复算，仅4083的CLEAN→REVIEW，所有策略处置完全相同，原始Job/模型输出保持。新增0模型调用，不计新准确率样本。证据：gateway-policy-alignment-{red,green}.log、gateway-policy-alignment-real-replay.json。

## 无法解析的网关响应未封闭未知用量

协议Mock复现：HTTP请求已发出，但网关返回非JSON内容时，ValueError早返回发生在UNKNOWN预算标记前，预算会误留NOT_CALLED。该错误不是本轮真实接口故障记录，而是验收补充的确定性边界复现。

新增两项测试先得到1失败/1通过：非JSON响应应为UNKNOWN、后续受限请求不得发出；另一项确认接口已报告用量但模型JSON不合格时，实际Token仍应保留。修复把已调用且用量未知时的指标/预算更新移到所有异常早返回前，仍不退款。若usage已知则不误改UNKNOWN，未发送的预留仍可释放。默认未配置Token额度的有限旧重试行为不变。

相关33项/8.485秒通过；包括新网关配置、策略一致性、JSON解析、原预算与原重试测试。最终完整回归与源码哈希以gateway-standard-final-full.log/status.json及v1.3-current-source-manifest.json为准。原482项及485项是对应中间版本记录，不冒充最后一次验证。

这两项修复都不会让之前拒绝的图片自动获得执行许可。新网关的几何/质量任务仍有超时、泛促销及包装保护仍会暂缓，真实可执行方案的最终预演成功与批量放行仍未验证。
