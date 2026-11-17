# 重新审核历史原图

`audit-snapshot`读取旧Job封存的商品/图片快照，以当前DeepSeek配置和提示词建立新的只读审核Job。它复用现有V2全图审核、模型客户端、缓存键、账本和报告，不重新实现图片内容判断，也不读取线上商品。

```powershell
.\run.cmd audit-snapshot --source-job D:/GitHub/MyE-C-skill/automation/data/process-5183-5173-20261117/jobs/JOB_13f22fd345f74a258f933d57b005c22a --pid 5173 --shop 7 --config-dir D:/GitHub/MyE-C-skill/automation/local --data-root D:/GitHub/MyE-C-skill/automation/data/reaudit-5173-20261117 --instruction "按新版提示词重审5173的原始图片，包括已删除图"
```

原图库中的图片可能已被删除，因此重审当前线上图库与重审历史原图是不同范围。此入口覆盖指定源Job的原始图片、SKU引用及正文商品图片，排除正文文字和footer；source_job_id、每个源文件SHA、商品/店铺、历史账户绑定及本次新指令都记录到snapshot_origin.json。账户身份来自已验证历史快照，不能冒称本轮重新登录验证。

源Job、输入状态和每张原图必须通过既有证据清单及实际SHA校验。新输出不能位于源Job内，错商品/店铺、缺失原图或证据变化会拒绝。新的模型调用使用当前本地密钥和配置、当前单DeepSeek策略及一个新的audit模式Job/预算；不复制旧授权、结果或账本。原图只复制到新证据目录，旧文件前后校验不变。

输出AUDITED只表示本轮语义输出完整，不表示商品已经整改或线上已恢复。REVIEW_REQUIRED表示仍有模型待复核或格式/请求问题。每张图的原始JSON在full_ai_judgements/full_ai_metrics，结构化总结果在snapshot_result.json。通过普通results命令可只看最终JSON，不展示思考内容。

此入口没有上传/保存/回滚/去字/标题生成路径，不会自动把历史图片重新放回商品。确认新判断和可执行修复后，线上恢复与整改仍需在正确当前状态绑定的独立任务中执行；不能拿历史快照当作当前商品直接保存。
