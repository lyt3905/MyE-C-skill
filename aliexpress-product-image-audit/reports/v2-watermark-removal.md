# V2本地水印算法

## 当前：Q01–Q24已授权真实只读回归

Q01–Q24的24张本地原图真实只读回归已结束：47次请求（仅DeepSeek/MiMo，无重试），最终动作REVIEW 23、KEEP 1；取得有效输出44条、未取得有效输出3条（含请求失败和格式错误）。本批网关已知Token 350370，未知usage 1次，费用null，仅记录。线上访问、上传、保存、删除和本地整改均0。完整目标仍未完成。

最新结果入口v2-qbatch-acceptance.md。805项离线测试源绑定未变；17份报告的以下旧记录均按原日期和源码检查点保留。OpenCV/完整LaMa已配置，普通本地去字不需要外部编辑配置。

## 前轮本地记录（历史原文保留）

最新完整离线回归：795 项通过，失败/错误/跳过均为0；run_id=1b76237b9bee4738a13a44366b72b38b。测试期间源码一致，无网络尝试；本轮真实模型调用及线上写入0。详见 v2-evaluation-full-tests.log、v2-evaluation-tests-status.json 和 v2-evaluation-test-source-manifest.json。783 项记录仅作为上一版源码历史检查点保留。

AI提供归一化bbox/polygon及语义；程序生成二值mask、膨胀2px、校验面积≤配置上限和保护区。只有OWNED_OR_LICENSED可修复。工厂/商品/包装印刷、署名和未知文字不能被当作可擦覆盖字；无外部找原图。

小面积平滑背景使用OpenCV Telea；预设NS备用一次。复杂区域使用显式本地LaMa路径；缺失则LAMA_UNAVAILABLE/REVIEW，不下载权重或无限重试。原图只读，输出新PNG、mask、算法参数、输入/输出/mask SHA及时间。

续作新增RGBA处理，mask外RGB及alpha不变；丢失透明度的候选拒绝。LaMa按已安装simple-lama的forward(image,mask)或声明的字典契约加载，记录模型SHA和契约；两种形式均通过真实torch.jit加载的合成计算图测试。这些不是训练LaMa效果。

依赖及.partial文件清单见v2-followup-local-runtime.json；完整实际权重未配置。本轮合成before/after/mask保存在work/v2-followup-20261115/samples；RGB旧样本保留在初轮目录。不得把蓝色矩形等合成图片当真实商品效果样本。
