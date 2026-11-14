# 8788源码版本核对

本轮开始时审核项目git status无未提交改动；原分支codex/gateway-output-diagnostics-20261113，HEAD `8399a4eb2c213c43cbebd0350de601556d9eb052`。专用本地修复分支：`codex/8788-contract-local-fix-20261114`。本轮没有从GitHub下载或覆盖源码，没有提交或推送。
原审核清单记录的是Windows原始字节SHA；此前已保存的逐文件核对将其与Git LF blob对应。本次用本地不可变Git对象核对7个重点文件，基线LF文本全部与原审核快照记录相同。
baseline-source目录是从该HEAD读取的基线副本，不冒充历史进程载入文件；下表“当前本地”是修复后的实际字节。

| 文件 | 历史manifest SHA256 | 基线Git blob SHA256 | 当前本地SHA256（修复后） | 结论 |
|---|---|---|---|---|
| scripts/full_product_audit.py | bf08e602be9f3d67a6a5733727375b541fb19009467dcf5070cef78f5f40a341 | bf08e602be9f3d67a6a5733727375b541fb19009467dcf5070cef78f5f40a341 | 7312d0c68411d6f86dda58f6c3717f1d17be7b2119b59f28c15fa8fd680312b7 | 本轮有意修复；基线LF对应已核实 |
| scripts/full_audit_recovery.py | 846030937d7a409cd8218b54b302eba3409a9b398ea5223088670c08cba79a9c | 846030937d7a409cd8218b54b302eba3409a9b398ea5223088670c08cba79a9c | 27d5a4cc1e49bb5eaece2476ef70e1321d70fb5985d9912375326abe75ca2ba2 | 本轮有意修复；基线LF对应已核实 |
| scripts/ai_judge/watermark.py | 55e76c96cedb49e01ca318dd94d868627bd9e69601fccda1af994218745b7db9 | 7b616df17e5815daae57af6cc26b4172c4fbc38694dc631dd11f47508a147b61 | 30046186528b3829c370ddfa9147b7402ada15d6901556d5be8f2655975e0366 | 本轮有意修复；基线LF对应已核实 |
| scripts/ai_judge/product_identity.py | d520ffc022ed6ab0358f9728a02074657c620d7c82a1e10e120b0b6ae2adee14 | 540c4883a5dc2c654e3af554189fd8ecfe55132845273d1108c04af9fda1f01c | 59259b358bca624e6ade67ec2fcff09cff31620231662eac638642bd9df69182 | 本轮有意修复；基线LF对应已核实 |
| scripts/ai_judge/schemas.py | 37862ebb138eb1c26620841d83abaa46add3df4d8c4cbcd4236dac8333ed76df | 8912a24d4e0b282491e9d2f837795be1c33e7c2b7b1c68cc84d511cddb1f8e2a | 049bdd7c9d39d12a38aabd348cb3e383d0ef5e1283f2a4be49beb5e8c16a5a95 | 本轮有意修复；基线LF对应已核实 |
| scripts/ai_judge/client.py | bc4ad9a21136eec41927d441c74d7cb6bf2a9718f91425c66a19627158e6de78 | e863bc6fee01d03b9ffa9c81da4ec7db6688d8e0b6c8ad06bb0073fd9151463e | 9d2f9051872e1a47ee5709d139f6d697f555641379c4fb3a4ffdbd4ff9b9a918 | 本轮有意修复；基线LF对应已核实 |
| scripts/evidence_builder.py | e885ea2d633038bb860f6a4dccee295fa697a934b5ac9982b2de985bc382d513 | 30b83432fa662930e1bdd00fa90dffd3b008bc8910981066d7a5ca0ded481d24 | e885ea2d633038bb860f6a4dccee295fa697a934b5ac9982b2de985bc382d513 | 源码内容未改；原始字节/换行分别保留 |

433个原始Job/续跑文件已做完整性封存；parent_bindings原有9项校验通过。本地诊断前后全树内容哈希一致。完整性校验只将文件作为不透明字节，不解析固定描述字段。
原始结果、置信度、预算和请求账本均未改；旧28次授权仍已消耗并关闭。
无法追溯确认：历史进程实际已加载模块、pyc、依赖版本及每个调用时刻的内存状态。旧运行没有逐进程证明，本次不补造这类证据。
固定描述及其图片/文字不作为诊断输入；本地报告根据full_inventory和队列的三类图像/SKU引用重建最小元数据，未解析audit_product.json。
