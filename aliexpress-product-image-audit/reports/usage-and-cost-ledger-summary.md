证据日期：2026-11-14；源码基线：20ecfe83e307bbe15e7e298954a7c57d90dcdca6；对照 a14669ba76aae5dbf72b00afe83b8028dc3cba97。
本轮范围：单Agent，本地开发/Fake/Mock；无真实模型或站点操作。最终本地验收见 automation-final-acceptance.md；Fake与真实证据严格分开。

# 用量与费用账本

本轮业务真实模型请求0、审核Token0、模型费用0（无请求）、站点读取0、上传0、保存0、真实整改0。Codex开发会话本身用量不属于商品审核模型账本。

可用路由价格和未来Canary费用UNKNOWN；USD授权预算null、配置disabled。历史网关177351Token属于旧Job，不转入本轮预算，不认作供应商核实账单。

来源分类：PROVIDER_REPORTED_VERIFIED需要独立来源证明（当前无）；GATEWAY_REPORTED_UNVERIFIED仅网关数字；CLIENT_ESTIMATE估算；MISSING缺失。STRICT不能用网关数字放行。CONTROLLED模式明确软预算而非硬上界；预留、DISPATCHED、SETTLED/UNKNOWN与price/policy/Job绑定持久保存于既有BudgetManager账本。未知usage为null，保留费用/Token预留并停止。请求失败不退次数、不自动换模型。
