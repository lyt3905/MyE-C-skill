# SKU图片按包装分别选择

规则入口：src/mye_c_automation/sku_assignment.py 的select_v2。正式V2整改继续使用这一入口，无需额外开启新选图开关。

- no retail box：从本商品已有且审核KEEP、清晰完整、尺寸可用的非盒子商品图中选择，实际retail_box_status必须ABSENT。
- with retail box：优先符合条件的盒子图，实际retail_box_status为PRESENT。
- 没有可用盒子图且有两张合格非盒子图：给现有两个规格分别分配不同内容的图；有盒规格的source_retail_box_status仍记录ABSENT，不能伪造盒照。
- 不同URL但同SHA只算一张图；不足时明确记录缺图，不把盒照分给无盒规格，也不重复一张图掩盖不足。

保留现有SKU ID或显式启用的整行哈希绑定，不创建SKU，不改名称、originalBox、价格等非图片字段。同款和置信度仍仅记录，REVIEW/UNCERTAIN图片不能用来凑候选。

旧错误是发现盒子图后只处理有盒行，漏掉无盒行。0.2.8改为同一次计划分别匹配两个规格；独立回读除URL/字节外，还核对每行的可见包装状态及两张图片内容不同。

5099已使用原有封存审核结果建立新SKU纠正Job：原模型回复和账本只读引用、不复制为新审核，不重新调用模型；当前快照和所选图片字节重新核验。现有Plan编译器提供受限SKU纠正入口，仍走LocalExecutor和ExecutionLedger；仅改变SKU池和引用，一次保存、零上传，主图/详情/正文保护。证据见reports/sku-split-5099-20261116/。
