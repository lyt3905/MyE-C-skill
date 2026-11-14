# 业务规则回归
现有policy/compiler测试继续通过，KEEP保护、未知review、盒照与SKU规则保留原SOP；OCR明确禁用阻编译，模板不确定入候选；不自动擦除，不自动改状态/发布。
人工review必须绑定job/pid/shop/evidence hash，未处理项目禁止编译；compiler只允许既有字段白名单。描述URL继续保留现有机制，未新增未经授权外链转存。
