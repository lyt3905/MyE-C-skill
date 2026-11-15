# SKU候选、分配与平台能力

IMPLEMENTED / FAKE_VERIFIED。有盒：同商品关联与零售盒≥0.80，候选按玩具+盒/清晰度选择，绑定现有With Retail Box SKU真实ID，不新建SKU或改规格/价格。无盒：两张不同SHA合格玩具，明确身份、清晰完整、无未处理店铺/未知文字；不足数量如实报告，不用UNKNOWN凑数。

现有writer实际使用单URL引用，双候选均进入SKU图片池，最佳一张绑定现有引用；SITE_SINGLE_IMAGE_REFERENCE代表该writer限制，不代表已经核实平台没有其他接口。capability_evidence记录当前快照字段和writer能力，other_interfaces_verified=false、second_reference_assigned=false，不宣称两张均已绑定SKU。

旧真实只读快照：v2-full-workflow-platform-evidence.json，skuImageUrl观测为字符串，商品各图片池为列表。它证明既有协议形状，不是本轮新接口验证。其他SKU更新接口/数组引用/前端展示一致性仍BLOCKED（本轮未授权新线上读取），不可编造接口字段。

本轮with_retail_box / without_retail_box的完整Fake Job及候选、SKU_ASSIGN计划和回读见v2-full-workflow-fake-evidence.json。
