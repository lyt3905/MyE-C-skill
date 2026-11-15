# PID4086剩余促销文字条已补删

日期：2026-11-15（Asia/Shanghai）。用户追问“别的该删除的你没删掉吗？”，本次在既有PID4086完整图片整改写入授权范围内核对并完成剩余一项。

## 真实结果

- 补删原详情第1张红色促销文字条，源SHA256 df1cd09fa06dd466f8a778e5d061de92bfe42b8691e3fe4c75e19378641fbfe7。
- 该图原DeepSeek明确建议DELETE，旧程序因文字归属UNKNOWN错误暂缓。没有新增模型调用，没有改写原响应或账本。
- 本次真实保存1次，上传0；详情图10→9。主图、已修复的店铺水印图、SKU池和SKU引用均保持不变。
- 独立登录会话回读通过：17处当前图片/引用字节全部正确，Description及其他业务字段不变，presale仍true。
- 原始DeepSeek建议删除的3张图片（红色促销条、黄色购买须知、绿色售后说明）现均不在商品图片引用中，剩余原始删除建议0。

当前独立任务JOB_e968b18b3aad41e998ce711f4ba09b27，状态FINISHED / AUTO_VERIFIED，仅表示这一项补删及回读通过；未声称重新调用模型全量审核。

## 程序修复

仅对模型明确DELETE、类别为文字/信息图、没有玩具、没有零售盒的整图删除，取消未知文字归属的额外拦截。保留owner=UNKNOWN，不编造归属；不把未知归属本身当作删除依据。

商品照片上的未知文字仍不会因此自动授权擦除或删除；明确KEEP不转DELETE，明确弃权或包装不确定仍保留。提示词同步说明纯店铺通知/促销条与有用产品图片的区别。

新增5项回归；修改前2项因原拦截失败，修改后206项相关离线回归通过，失败/错误/跳过0，运行ID b9557aea26974bd4819c4ad302a0d323。源码绑定前后一致，网络尝试0。本次未重新执行整个项目全量测试。

## 证据

- work/v2-delete-promo-4086-20261115/captured-decision-reassessment.json：已有真实AI删除建议的程序重评，不是新增模型调用。
- authorization-context.json：本次任务与原图片整改授权的范围。
- run-status.json、execution.log：实际一次保存及最终回读。
- jobs/JOB_e968b18b3aad41e998ce711f4ba09b27：补删计划、执行前后快照与独立图片字节校验。
- reports/v2-delete-promo-4086-tests.log、tests-status.json、test-source-manifest.json：本地回归与源码绑定。
- reports/v2-delete-promo-4086.patch、manifest.json：本轮增量与校验。

原17次审核、预售恢复、主图水印修复等历史Job、响应与账本均保留。未暂存、commit或push。
