证据日期：2026-11-14；源码基线：20ecfe83e307bbe15e7e298954a7c57d90dcdca6；对照 a14669ba76aae5dbf72b00afe83b8028dc3cba97。
本轮范围：单Agent，本地开发/Fake/Mock；无真实模型或站点操作。最终本地验收见 automation-final-acceptance.md；Fake与真实证据严格分开。

# 按动作准确率

本轮真实评测 NOT RUN。没有新增人工真值、独立图片或SKU样本；TP/FP/FN/TN、精确率、召回率下界、暂缓率均N/A，不能填0或100%。

历史可靠基准仅7张（3正/4负），无SKU正例；重复请求和同SHA位置不扩大独立样本分母。历史5093单次替换不是动作级准确率。

REPLACE_TWIN/REPLACE_LOCAL/CROP_BANNER/ERASE_LOCAL/DELETE_REDUNDANT/SKU_ASSIGN均未凭本轮获得生产白名单；每类至少30确认样本、98%精确率、无严重误删，SKU须独立样本。保留原厂Logo、印刷、包装、摄影师/社交署名保护与0.90双模型门槛。
