# V2.0 当前证据哈希核对

最新完整离线回归：795 项通过，失败/错误/跳过均为0；run_id=1b76237b9bee4738a13a44366b72b38b。测试期间源码一致，无网络尝试；本轮真实模型调用及线上写入0。详见 v2-evaluation-full-tests.log、v2-evaluation-tests-status.json 和 v2-evaluation-test-source-manifest.json。783 项记录仅作为上一版源码历史检查点保留。

当前783项标准回归的源码前后及交付SHA一致，见 v2-followup-test-source-manifest.json。

原433份证据及旧Canary的11份文件全部未变，原Job、响应、账本和授权未复用或重写；详见 v2-followup-historical-evidence.json。

本次23份Fake Job/1163文件在复制时逐一核对SHA；每份archive清单位于 work/v2-followup-20261115/evidence。复制品保留原始字节及原临时路径，不是新的可复用授权Job。原760/774源manifest只对应历史源码，旧源码/报告副本和原测试日志保留。
