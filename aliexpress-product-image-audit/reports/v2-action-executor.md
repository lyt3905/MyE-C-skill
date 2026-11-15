# V2动作执行与集成

## 当前：Q01–Q24已授权真实只读回归

Q01–Q24的24张本地原图真实只读回归已结束：47次请求（仅DeepSeek/MiMo，无重试），最终动作REVIEW 23、KEEP 1；取得有效输出44条、未取得有效输出3条（含请求失败和格式错误）。本批网关已知Token 350370，未知usage 1次，费用null，仅记录。线上访问、上传、保存、删除和本地整改均0。完整目标仍未完成。

最新结果入口v2-qbatch-acceptance.md。805项离线测试源绑定未变；17份报告的以下旧记录均按原日期和源码检查点保留。OpenCV/完整LaMa已配置，普通本地去字不需要外部编辑配置。

## 前轮本地记录（历史原文保留）

最新完整离线回归：795 项通过，失败/错误/跳过均为0；run_id=1b76237b9bee4738a13a44366b72b38b。测试期间源码一致，无网络尝试；本轮真实模型调用及线上写入0。详见 v2-evaluation-full-tests.log、v2-evaluation-tests-status.json 和 v2-evaluation-test-source-manifest.json。783 项记录仅作为上一版源码历史检查点保留。

五动作继续使用原auto_workflow、compile_auto_plan、plan_v2、LocalExecutor和ExecutorService。KEEP不上传；DELETE只移除目标引用且保留原证据；REMOVE_TEXT经权利和质量门禁；AI_REGENERATE仅调用显式配置的编辑能力；REVIEW保留原因并允许独立动作继续。

本次补齐：修复图上传地址解析后的SKU核对；引用专用修复图追加到已支持的SKU池；仅引用DELETE由有授权且真实ID明确的SKU换引用完成并在计划声明DELETE权限；图片池删图的必要SKU替代必须同时出现在计划。

最后一份同商品零售包装证据不自动删除；有保留素材时绑定其原位置/SHA，编译防止同时删掉保留位置，写后独立获取实际图片核对SHA。缺SKU ID时保持SKU引用原样，主/详情独立修复走原执行器的引用保护能力。

图像编辑现在可由image_options中的本地适配器文件、已选模型、固定SHA配置，实际调用仍经过JudgeClient.invoke_image_adapter/BudgetManager，不新增HTTP客户端。缺少真实服务或已核实编辑能力仍暂缓；配置用法见docs/image-edit-adapter-v2.md。
