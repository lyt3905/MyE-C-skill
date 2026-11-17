# MyE-C Automation

0.2.21新增[历史原图只读重审](docs/snapshot-reaudit.md)，用当前提示词重审已封存、包括线上已删的原图；复用既有V2审核器，输出新Job，不自动恢复或写商品。

0.2.20修正[水印商品图的处理边界](docs/watermarked-product-images.md)：重复店铺水印和厂家原有边框不能直接触发整图删除；优先同原图替换或去字，无法安全处理时待复核。独立店铺商业宣传布局才适用宣传图整删规则。

0.2.19采用[图片内容由 DeepSeek 决定](docs/model-directed-images.md)：AI给出图片属性、最终动作及文字区域的保留／去字指令；程序负责固定业务规则与执行回读，不再按类别、文字归属或边框面积改写AI结论。历史回复和账本保留。

0.2.16新增[DeepSeek标题生成与图片流程合并](docs/deepseek-title-workflow.md)，规则仅参考独立 `title-rewriter/` 目录。启用 `allow_actions.TITLE_REWRITE` 后，原 `process` 命令同时处理英文标题；用 `fake --scenario twin --with-title` 可离线演示。

历史0.2.16完整隔离回归1060项及五个Fake流程通过；原Skill和开发源码在验证时不可访问。该版本交付时新标题功能尚未进行真实模型/线上写入验证；后续状态见[项目状态](docs/PROJECT_STATE.md)。

独立的 AliExpress 商品图片 V2 自动化软件，业务基准为 `68e168f1a08c6338cb0964dffbd021bb5e484556`。原 Skill 不参与安装或运行。

当前交付版本 0.2.21，以命令行和运行配套为范围：配置初始化/离线检查、独立权重安装、部署审查、同照片替换权限和旧模板资源。图片下载与回读使用[统一完整请求标识](docs/image-http-profile.md)。同时支持[已知保存成功的部分任务续办](docs/verified-partial-followup.md)、[SKU图片按包装分别选择](docs/sku-image-selection.md)、[下载失败重试](docs/download-retries.md)及[七张主图预处理/宣传图规则](docs/seven-main-and-seller-posters.md)。图形界面按用户选择推迟到下一轮，草稿保存在 `experimental/desktop/`，不随当前软件安装。历史报告保留。

上传地址支持后台地址末尾带斜杠。首次上传明确被拒绝、且尚未进入商品保存阶段的任务，可由受限续办接口建立新任务；保存结果未知时仍禁止盲重试。详见[上传失败与续办](docs/upload-recovery.md)。

已修复[明确店铺宣传图删除结论被程序错误降级](docs/explicit-poster-delete.md)的问题；模型原回复和历史账本保持原样。

支持[人工复核指定空白详情图的受限保存](docs/reviewed-blank-deletions.md)，不连带修改未授权图片，局部保存与整件验收分别记录。

现在支持[一条命令完整运行](docs/one-command.md)：

```powershell
.\run.cmd process https://39.107.244.239/products/5182
```

程序自行完成配置和密钥加载、下载重试、审核整改、SKU选图、受限保存和新登录会话独立回读，无需 Agent 衔接。5182 专用本地配置沿用已确认范围；其他商品需配置对应策略。`--audit-only` 仅审核，`--resume JOB_ID` 处理同一任务的中断恢复，未知保存不重复写入。

当前交付范围、逐项验收和后续限制见 [交付状态](docs/DELIVERY_STATUS.md)。

0.2.15 提交前完整离线回归：1043 项通过，失败、错误、跳过和网络尝试均为 0。从实际 Git 暂存内容检出的四个 Fake 场景均通过；固定夹具按原始字节保留，避免跨平台换行转换破坏证据校验。这些结果不代表所有真实商品或生产环境均已验收。

当前本机按用户选择启用10图并发；软件支持1–10并发。保留低推理强度、下载限速/成功缓存和最终JSON展示，见 [运行设置](docs/runtime-tuning.md)。

Windows 开发目录可以直接使用：

```powershell
.\run.cmd configure init
.\run.cmd configure check
.\run.cmd doctor --config-dir .\local
.\run.cmd fake --scenario twin
```

初始化不会覆盖已有文件。账号请填写到本地 `local/site.local.json`，网关请填写到 `local/model.local.json`，密钥通过当前窗口的 `$env:VLM_API_KEY` 提供。检查不会登录后台或请求模型，缺少配置时退出 2 并列出缺项。具体操作见 [配置与准备说明](docs/configuration-and-readiness.md)。真实验证须按[独立提案](docs/real-validation-proposal.md)另行授权。

需要 Python 3.12+。在本目录安装：

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -e .
.venv/Scripts/python -m mye_c_automation --help
.venv/Scripts/python -m mye_c_automation doctor
.venv/Scripts/python -m mye_c_automation fake --scenario twin
```

安装后也可用 `myec-automation`。从任何工作目录运行均可。`fake` 使用程序生成图片、Mock DeepSeek、内存商品和独立 Fake reader；不会请求模型或访问线上商品。支持 `twin`、`frame`、`repair`、`keep`。输出一条 JSON，包含 Job ID、业务状态、Fake 保存/上传次数及报告位置。成功退出码 0，参数或配置错误 2；业务暂缓请检查 JSON 的 `status`，不能仅凭退出码认定整改完成。

默认开发数据在本项目 `data/`；wheel 安装后默认用户应用数据目录。可设置 `MYEC_DATA_ROOT` 或使用 Fake/status 的 `--data-root`。Job 自带预算账本、模型原始结果、内容 SHA 缓存、计划和独立回读证据；全局执行账本和上传节流在独立数据根下。新数据目录不导入旧授权、Job、账本或凭据。

```powershell
myec-automation status JOB_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
myec-automation workflow -- --help
```

`workflow` 委托唯一的既有工作流，提供读取、预演、受限执行和恢复接口；它仍要求明确站点配置、策略范围和执行授权。早期 5094 只读测试的授权和结果属于历史阶段；当前商品状态以对应任务报告为准。请勿将 Fake 通过理解为生产就绪。

完整离线回归（包含原发现集）还需可选兼容依赖和本地 TorchScript 测试依赖：

```powershell
.venv/Scripts/python -m pip install -e '.[lama,legacy-ocr]'
.venv/Scripts/python -B scripts/run_tests.py
```

Prompt、Schema 和配置随包安装在 `mye_c_automation/config`、`mye_c_automation/prompts`；`resources.resource_path()` 提供统一定位。配置示例不含密钥。编辑自己的配置副本，不改安装资源。LaMa 权重自行安装，参见 [模型配置](models/README.md)。开发模块地图见 [架构](reports/architecture.md)，完整验证和限制见 [验收报告](reports/migration-acceptance.md)。

Git 仅保留程序、文档及必要固定测试资源。`local/`、运行数据、模型权重、构建产物和现场运行报告留在本机；报告中的本机证据链接用于对应运行环境，克隆仓库后需自行运行测试生成。保留的迁移报告是历史阶段记录，当前版本与限制以本说明和 `docs/PROJECT_STATE.md` 为准。

只读保留的旧双模型验收兼容模块仅用于历史回归，不是当前 V2 策略。V2 仅 DeepSeek、置信度 RECORD_ONLY、未知 usage 为 null；正文商品图片纳入审核，正文文字/footer/样式及非图片字段保护。
