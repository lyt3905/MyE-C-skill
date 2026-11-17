# 输入商品链接，程序自行运行

0.2.16起，可按[标题配置](deepseek-title-workflow.md)启用DeepSeek标题生成。已批准标题与图片整改合并保存并独立回读；标题警告/失败时保留原题，图片流程继续。

在 automation 目录运行：

```powershell
.\run.cmd process https://39.107.244.239/products/5182
```

安装包使用 `myec-automation process https://39.107.244.239/products/5182`。

配置完成后，只需要这一条命令。程序自行读取配置和密钥、核对店铺、处理恰好七张主图的规则、下载和重试、调用 DeepSeek、优先匹配同照片干净版本、去水印及质量检查、分别选择 SKU 图片、预演、上传保存，并用新登录会话独立回读。无需 Agent 编写临时脚本或逐步衔接，不在各阶段等待确认。无法确定的项目保留并列入结果，不强行删除或修复。当前为命令行，图形界面仍按此前选择后续再做。

## 配置一次

默认开发目录 local；独立安装后为用户应用配置目录。`--config-dir` 或 `MYEC_CONFIG_DIR` 可指定，不依赖命令的工作目录。

| 文件 | 内容 |
| --- | --- |
| site.local.json | 后台 base、账号 user、密码 pwd；商品链接必须属于该后台 |
| model.local.json | DeepSeek 网关、输出上限、推理强度和审核并发 |
| model-key.local.json | `{"VLM_API_KEY":"本地填写密钥"}`；已有环境变量优先 |
| automation.local.json | enabled、店铺/商品范围、动作开关和每任务限制 |
| image-options.local.json | 图片修改权利、掩膜上限和独立 LaMa 权重 |
| download.local.json | 下载间隔、重试次数和退避时间 |

支持按商品配置：`local/products/5182/automation.local.json`、`local/products/5182/image-options.local.json`。存在时仅覆盖该商品的对应设置；模型、后台、密钥、下载设置继续读取公共目录。权重相对路径以 image-options 文件所在目录为基准，建议填写软件内独立权重的绝对路径。

本机根据 5182 既有授权准备该商品专用配置：启用已授权的删除、同图替换、本地修复、SKU 同步，记录已确认图片修改权利，禁用外部 AI 重绘。公共执行开关和公共 RIGHTS_UNKNOWN 保持原样，未扩大到其他商品。新增商品应配置对应范围。

密钥只临时提供给本次运行，结束后还原环境。标准输出只有最终结果 JSON；运行提示写到标准错误和 process_events.jsonl。原始回复、思考和账本保存在 Job，不会打印密钥。

## 只审核与恢复

```powershell
.\run.cmd process https://39.107.244.239/products/5182 --audit-only
.\run.cmd process https://39.107.244.239/products/5182 --resume JOB_实际任务ID
```

只读模式不处理主图预删除，不上传、不保存。恢复必须匹配原链接、模式、策略和商品配置；已完成任务返回原结果；保存结果未知的任务只回读，不重复保存。七张主图预处理阶段响应丢失时，使用输出的该阶段 Job ID 恢复：先确认已保存结果，再自动创建正式审核 Job 继续运行。原阶段证据保留。

对于保存已确定成功、仅部分图片未能读取的任务，程序独立核对旧写入范围与当前状态，再通过既有受限续办机制建立新任务。旧 Job 和账本保留。新版本登记任务位置；非常早期旧任务若没有登记、也不在当前 jobs 下，会报告 PREVIOUS_JOB_EVIDENCE_REQUIRED，不猜测位置或重置账本。

`--shop 7` 可固定店铺；不填时读取当前登录店铺并按策略核对，不切换店铺。`--data-root` 指定运行数据目录。

## 结果

最终 JSON 给出 Job ID、报告路径、上传/保存次数、模型调用和已知用量、待复核项及独立核验结果。

| 状态 | 含义 |
| --- | --- |
| AUTO_VERIFIED | 本任务完成、独立回读通过，无待复核项 |
| PARTIALLY_AUTO_FIXED | 已执行可确定整改，仍有待复核项 |
| REVIEW_REQUIRED | 未读图片、核验失败或其他待复核情况；查看 technical_status 和报告 |
| APPLY_UNKNOWN | 保存结果未确定，只能回读恢复 |
| AUDITED | 只读审核运行结束，不代表已经整改 |
| FAILED / ERROR | 运行或配置失败 |

退出 0 表示得到明确结果，仍需看状态；2 为配置/运行错误；3 为未知写入、占用或尚未完成的写入阶段。`whole_product_clean=false` 时不能声称整件完成。主图预处理与正式审核分别最多保存一次，因此触发七图规则时可有两个保存阶段。

本轮开发使用离线 Fake/Mock 验证，不为演示新入口再次调用 5182 真实模型或修改线上商品。新入口的生产验收与该商品原有待复核项分别记录。
