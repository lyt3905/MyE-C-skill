# V2图片整改及同原图版本识别 GitHub交付

用户于2026-11-16明确要求推送GitHub，本次提交现有开发分支中本项目尚未提交的累计V2修改，包含DeepSeek单模型、置信度仅记录、正文商品图片与SKU引用同步、非图片字段/预售保护、经验规则复用，以及同一原图不同版本识别和替换优先。其他项目修改不提交。

整改顺序：已有KEEP干净同原图版本优先替换；无替代时大面积店铺宣传边框删除，其他明确覆盖字进入局部修复及质量复核。模型初审不改写，最终计划单独记录。新功能为IMPLEMENTED/FAKE_VERIFIED，同原图检测另有真实本地CV证据；新模型/线上部署写入NOT_RUN，不宣称PRODUCTION_READY。

- [最新验收报告](v2-visual-versions.md)
- [完整931项离线测试摘要](github-visual-versions-full-tests-summary.json)
- [推送前54项复验](github-visual-versions-prepush-tests-status.json)及[日志](github-visual-versions-prepush-tests.log)
- 全量日志：[307项](github-visual-versions-full-shard-0.log)、[326项](github-visual-versions-full-shard-1.log)、[298项](github-visual-versions-full-shard-2.log)
- [测试文件绑定](github-visual-versions-tested-source.json)：完整回归后仅清理两个测试文件末尾多余空行，语法树一致；相关测试和新规则共54项重新通过，其余源码/提示词/样本未变；不发布本地运行缓存、真实原响应、凭据或账本。
- [3527离线重放](github-visual-versions-3527-offline-summary.json)：主图1优先替换为详情2（总览7）的干净版本，总览11的不同姿势照片被排除。新真实模型调用和线上读写均0。

原有历史报告及本地Job保持原样。部分旧报告引用本机work证据，此类证据按原有忽略规则留存本地；本次可在GitHub直接查看以上精选测试证据。发布代码不代表部署线上审核服务或修改线上商品。
