# 图片内容由 DeepSeek 决定

0.2.20进一步明确了[水印商品图与店铺广告的区别](watermarked-product-images.md)，图片内容仍由DeepSeek判断。

从0.2.19开始，正式V2流程采用模型决定图片内容、程序执行和校验的分工。已有CLI和配置入口继续使用；无需新建审核器或另一套运行方式。

| 事项 | 负责方 |
| --- | --- |
| 商品图、盒照、宣传图、通用说明、空白图、水印及文字归属 | DeepSeek |
| KEEP / DELETE / REMOVE_TEXT / AI_REGENERATE / REVIEW 和每个文字区域的保留／去字指令 | DeepSeek |
| 去字后残字、商品结构、包装印刷是否受损 | DeepSeek质量复核 |
| 七张主图预处理、主图数量、图片尺寸/格式、授权/动作开关、SKU规格绑定与不同图片分配、保留包装资料、引用同步、保存和独立回读 | 程序的固定规则 |
| 根据AI坐标建立掩膜、局部像素处理、同照片几何/字节校验 | 程序执行算法，不分类图片内容 |

程序不再根据边框面积和位置重判宣传图，不因visual_class=UNKNOWN、文字owner=UNKNOWN或包装属性UNCERTAIN单独否决AI明确动作，不把AI KEEP改成DELETE/REMOVE_TEXT。AI属性、理由、置信度和原始回复如实保存，decision_authority=MODEL标记决策来源。

## 文字区域

新提示词要求watermarks每项返回action=KEEP或REMOVE_TEXT。程序直接执行此指令，不再用kind/owner覆盖它；KEEP区域和preserve_regions保持保护。模型应明确保留厂家/商品/包装印刷、创作者署名及通用商品说明，并对需去字的区域提供准确坐标与repair_mode。旧回复缺少action时兼容已有区域标签，原文件不改写；缺少可执行目标仍不可擦除，不凭空造坐标。

JSON、绑定SHA、坐标范围、掩膜外像素、实际授权及可执行后端限制继续校验。程序不得无视AI提供的保护坐标，也不把明确REVIEW、abstain、响应缺失或格式错误转换成成功。历史几何宣传图规则只保留为离线历史兼容工具，正式decide/prepare不调用它们生成新结论。

## SKU与同原图替换

SKU可用性读取AI的is_toy_photo/is_retail_box_photo；盒子状态读取AI的retail_box_status。visual_class仅描述，不再用类别白名单、clear/subject_complete或水印标签再次否决AI KEEP和SKU可用性。AI的recommended_group=UNKNOWN仍保留为SKU待处理，不根据其他属性补造推荐组。程序继续按现有无盒／有盒规格分配、优先已有盒照、没有盒照时使用另一张不同的无盒图；不创建SKU，不重复图片掩盖不足，不把UNCERTAIN包装伪装成ABSENT/PRESENT。

同原图替换仍是已有固定优先规则：候选由AI KEEP批准保留，程序只校验有效图片格式和同照片几何/像素一致性，不判断图片中的商品或文字类别。无法证明同照片时按AI原动作继续。

2026-11-17 用户取消正式 V2 的最低像素尺寸限制：790 像素等可解码图片可用于 SKU、同原图替换和局部修复，执行器不再以短边不足 800 拒绝上传。不自动放大或补边。尺寸继续如实记录，用于像素对齐及候选排序；损坏格式、空白/透明候选、掩膜外改动、明确 AI REVIEW 和质量失败仍分别校验。历史 legacy 审核与补边工具保留其旧行为。

## 报告与历史

AI动作与程序执行阻断分开记录。例如AI DELETE且visual_class UNKNOWN现在仍为DELETE；若删除会清空必要图片池、缺少SKU替代引用或删除最后包装资料，则执行计划单独说明固定规则阻断，不改写AI回复。AI质量复核明确残字仍在时，候选仍不能上传；这不是本地语义重判。

本轮仅本地开发、历史回复离线对照和Fake验收。历史Job、原始响应与账本不迁移、不重写；不据此重跑5180或其他线上商品。
