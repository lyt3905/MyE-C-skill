# 历史人工标注恢复与本地OpenCV/LaMa配置

已恢复并SHA核对Q01–Q24全部24张，以及完整旧标签库47份独立图片：39份水印二元标签、11份明确整图删除指令（两类有重叠）。此前把当前V2空JSONL误当作全项目没有人工标注，现已纠正。已安装205803670字节完整LaMa权重，配置local/image-options.v2.local.json，并通过真实本地LaMa推理、OpenCV Telea/NS以及原完整流程的两条Fake上传/保存/回读验证。普通REMOVE_TEXT不需要外部image_edit服务。应用源码未变，仍匹配799项回归检查点；本次语义大模型请求、API Token及线上商品写入0。

## Q01–Q24可以复用

已找到reports/v1.3-confirmed-label-registry.json及各组原始用户确认记录，47份原图全部逐字节SHA核对一致，原始标签文件不改写。Q01–Q24：24份不同SHA，其中16份明确水印归属（7正、9负），10份明确整张删除指令；部分样本同时具备两种标签。Q19与此前D图同SHA，重复确认不多计；Q24是detail图片中的中文标题图，不是固定Description字段。

完整旧库还包含Q25–Q30等记录，共47份独立图片，39份水印二元标签（13正、26负）、8份二元归属未标注、11份明确整图删除指令。保留每项用户确认来源、原图路径、SHA、标签原义及动作标签。不能把“有水印”直接补成REMOVE_TEXT，也不能把“原厂内容”自动扩成所有五动作/包装/SKU真值。旧模型GLM/Kimi结果不冒充当前DeepSeek/MiMo效果。

恢复数据：本次任务目录reused-human-labels.jsonl及q01-q24-human-labels.jsonl；统计：v2-recovered-human-labels.json。这是标签库，不含伪造模型预测。后续用真实或既有选定模型预测按SHA匹配评分，用户无需重标同一批。当前PID5097的5份图片与Q01–Q24没有SHA重叠，原该商品无对应人工真值的记录不被追改；“全项目没有人工标注”的说法已纠正。

## 本地修复由项目配置，不向用户索取外部API

REMOVE_TEXT现有链路为：视觉模型给区域 → 本地mask → 小面积平滑背景OpenCV Telea/NS，复杂纹理或较大区域LaMa → 确定性检查及视觉质量复核。image_edit仅服务独立AI_REGENERATE分支，不是普通去水印的依赖。此轮按用户要求完成本地LaMa安装和配置，没有增加第三套Runner或客户端。

完整权重来自已安装simple-lama-inpainting包指定的发布文件：https://github.com/enesmsahin/simple-lama-inpainting/releases/download/v0.1.0/big-lama.pt 。下载到local/models/lama/big-lama.pt，205803670字节，ZIP条目CRC通过；计算并固定SHA256：7ba7aa7ac37a4d41fdbbeba3a2af7ead18058552997e3a3cd1a3b2210c9e6b4c。不覆盖旧缓存partial文件。本地实现支持该真实权重的forward(image,mask)契约，CPU实际运行成功，无外部图片编辑请求。

配置文件local/image-options.v2.local.json已写入本机路径及SHA，现有JobManager可直接冻结；现有run/full-audit参数 --image-options local/image-options.v2.local.json 使用该配置。保持原有授权字段，不因配置算法扩大线上权限。自建样本测试明确用自有图片权限；没有把该权限写进旧真实Job。

## 已实际验证的范围

1. 完整训练LaMa模型执行真实像素修复，保留mask、before/after、参数、耗时及输入/输出SHA；不再只是合成TorchScript计算图。
2. OpenCV Telea、NS和LaMa三个本地输出均通过确定性检查：尺寸/类型正确、输出有变化、mask外RGBA像素不变、原图未覆盖。
3. 复用tests/test_v2_workflow.py的现有整条流程，分别走默认OpenCV与实际训练LaMa。两条各模拟上传1、保存1，并完成内容回读；Description原值保持。模型分类/质量回答及站点在此流程中仍为Fake，不能声称真实商品视觉效果或线上验收已通过。
4. 799项源绑定296份未变，没有为只改数据与本地配置重复整套测试。新增运行验证日志local-runtime.log及v2-local-inpaint-runtime.json记录本次本地实际执行。

对比样本：本次任务目录samples/local-inpaint-comparison.png，左原图、中OpenCV、右训练LaMa。样本为自建图，真实商品去字效果仍应逐图质量复核。当前PID5097依然REVIEW，未改成通过，也未修改线上商品。

此前“需要用户提供编辑配置才能继续普通本地修复”的交接说明不准确，已修正。剩余工作是用恢复的用户标签做当前模型回归、继续真实图质量验证及后续授权阶段；全目标未完成，不能把局部运行成功写成PRODUCTION_READY。
