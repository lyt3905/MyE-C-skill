# V2 SKU包装盒与图片池选择

## 当前：Q01–Q24已授权真实只读回归

Q01–Q24的24张本地原图真实只读回归已结束：47次请求（仅DeepSeek/MiMo，无重试），最终动作REVIEW 23、KEEP 1；取得有效输出44条、未取得有效输出3条（含请求失败和格式错误）。本批网关已知Token 350370，未知usage 1次，费用null，仅记录。线上访问、上传、保存、删除和本地整改均0。完整目标仍未完成。

最新结果入口v2-qbatch-acceptance.md。805项离线测试源绑定未变；17份报告的以下旧记录均按原日期和源码检查点保留。OpenCV/完整LaMa已配置，普通本地去字不需要外部编辑配置。

## 前轮本地记录（历史原文保留）

最新完整离线回归：795 项通过，失败/错误/跳过均为0；run_id=1b76237b9bee4738a13a44366b72b38b。测试期间源码一致，无网络尝试；本轮真实模型调用及线上写入0。详见 v2-evaluation-full-tests.log、v2-evaluation-tests-status.json 和 v2-evaluation-test-source-manifest.json。783 项记录仅作为上一版源码历史检查点保留。

同商品零售盒PRESENT/SAME_PRODUCT且置信≥0.80时，从合格候选中优先玩具与盒同框，再选盒单图；未选盒图保留。无盒集合明确ABSENT时，只选合格且模型明确适用的TOY_PRODUCT，两张不同SHA、不同角度优先；缺图记录1_OF_2或0_OF_2，不复制。模糊盒关系/UNKNOWN不改成无盒。

两张无盒候选现在都会进入站点已有images.sku列表。真实SKU行优先保留候选中的原正确引用，否则绑定首选图。当前执行器只证明单行skuImageUrl能力，同SKU多图片引用未核实，仍记录SITE_SINGLE_IMAGE_REFERENCE；不伪造属性、变体、数量或第二字段。

只绑定已有唯一真实skuId/id。缺失/重复或映射不明时保留其原SKU引用；共享原图的主/详情修复可独立继续。删除被SKU引用的图时，必要的真实ID重绑必须在同一编译计划中；仅引用图片可以追加修复输出到SKU池，原始证据仍保留。

声明候选Schema已补齐SKU池URL、追加位置、源引用ID、必要换引用与保留包装来源，并用实际生成候选校验。测试见test_v2_repairs_sku、test_v2_completion和最终完整日志。真实包装分类准确率仍无标注数据。
