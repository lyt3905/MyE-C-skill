# PID4086 正文图片引用补删与独立回读

2026-11-15，shana1 / Shop 7 / PID4086。用户明确正文尾部附加内容保留，其余商品图片正常审核，并授权“开始执行吧”。

## 真实结果 REAL_VERIFIED

实际保存一次，上传0，新模型调用0。复用原DeepSeek对原详情第1、2、12张的DELETE判断，只删除descriptionJson中对应的三个独立图片节点：红色促销条、黄色购买须知、绿色售后说明。

新登录会话独立回读通过：正文商品图12→9，尾部附加图片2张及全部尾部内容不变，共11张正文引用。剩余9张商品图均对应原DeepSeek KEEP，当前下载字节与原审核SHA一致。尾部包装材料示意图与擎天柱引流图不纳入模型审核或整改，不将其标成AI通过。

正文文字与节点属性保留，图片池、SKU、预售true及其他非图片业务字段不变；仅服务端updatedAt按保存自然更新。读取全部11张当前正文图片成功。

## 根因与限定修复

旧任务仅删除images.detail引用，descriptionJson完全受保护，导致实际详情正文仍引用这3张图片。旧报告“全部删除”的结论只覆盖图片池，不代表页面正文，已经在本次纠正；历史报告、Job、模型响应和账本不改写。

新增description_images.delete_body_images：仅按明确获准的完整URL删除shopFooter之前type=image的顶层图片节点；不遍历文字、混合节点或footer。保存接口新增显式description_image_deletions，并绑定原商品状态；提交正文必须精确等于受限转换结果，不能夹带文字或尾部修改。默认保存仍禁止更改Description。

这次接通的是明确授权的正文图片删除路径。尚未宣称所有正式审核入口已自动采集、分类并同步正文独有图片，也未将本地修复部署到线上审核服务。商品数据已真实更新。

## 本地验证 FAKE_VERIFIED

新增10项测试，覆盖正文节点、尾部豁免、文字保护、非法修改拦截、过期状态拒绝以及Fake保存和独立回读。相关8个测试模块合计83项通过；不是项目全量测试。日志work/v2-description-4086-20261115/tests.log；修改前失败证据tests-red.log。

## 证据

- work/v2-description-4086-20261115/plan.json：三张图的原审核绑定及授权范围。
- before.json、desired.json、wire-body.json、independent-after.json：保存前、目标、实际发送和独立回读。
- status.json、execution.log：FINISHED，实际保存1次。
- description-image-readback.json：11张正文图片下载记录，9张商品图与原审核SHA一致。
- reports/v2-description-4086.patch、manifest.json：本轮增量及证据哈希。

不commit、不push，不触及其他商品。一次性执行脚本已有execution-claimed.txt，不能重跑。
