证据日期：2026-11-14；源码基线：20ecfe83e307bbe15e7e298954a7c57d90dcdca6；对照 a14669ba76aae5dbf72b00afe83b8028dc3cba97。
本轮范围：单Agent，本地开发/Fake/Mock；无真实模型或站点操作。最终本地验收见 automation-final-acceptance.md；Fake与真实证据严格分开。

# 模型分歧与未知保留

本轮真实模型 NOT RUN。Fake回归覆盖watermark类别/owner/区域分歧与单mark UNKNOWN、身份五维未知、SKU image_type/packaging/shared/missing字段分歧。

历史5097两次SKU补充调用中DeepSeek MIXED、Kimi BOX均MATCH，完整业务仍UNKNOWN；最新客户端补丁应REVIEW，不能改写原始模型结果。历史响应离线回放与本轮Fake分开记录，均不计新增真实调用。

完整审核桥接保留原始结果和evidence ID，将相同SHA映射到多个位置，未知项进入DEFERRED；完整审核INCOMPLETE不以较窄队列清除。

本轮读取5097补充Canary两份原始响应离线重放：客户端REVIEW、业务UNKNOWN、观察原值一致，旧目录封印未变。详见automation-sku-offline-replay.json；新增真实请求/Token均0。
