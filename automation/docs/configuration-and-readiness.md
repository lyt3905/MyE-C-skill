# 本地配置与运行准备

使用 `run.cmd` 或 `.venv/Scripts/python -m mye_c_automation`。所有命令委托同一个 V2 工作流。

```powershell
cd D:\GitHub\MyE-C-skill\automation
.\run.cmd configure init
.\run.cmd configure check
```

初始化在开发项目 `local/` 下创建 `site.local.json`、`model.local.json`、`automation.local.json`、`image-options.local.json`。已有文件逐项保留，不覆盖。wheel 安装后默认位于用户应用配置目录；可用 `--directory` 或 `MYEC_CONFIG_DIR` 显式指定。配置文件均不进入 Git。

填写 `site.local.json` 的 `base`、`user`、`pwd`。base 是 HTTPS 商品管理后台地址；不会从原 Skill 或其他目录自动找账号。不要把密码发送到聊天中。

在 `model.local.json` 配置实际模型网关地址；当前 V2 仅 DeepSeek。示例 8788 地址不代表网关已启动。密钥在当前 PowerShell 设置：

```powershell
$env:VLM_API_KEY = '你的网关密钥'
.\run.cmd configure check
.\run.cmd doctor --config-dir .\local
```

`.env` 不会自动加载。检查只输出密钥是否存在，不输出密钥或后台密码，也不登录、不请求模型。`ready_for_readonly=true` 只表示离线配置满足要求，不表示后台连接或模型语义已验收；`ready_for_write` 不会因为本地检查成功自动变为 true。

授权文件默认 `enabled=false`。其中 `REPLACE_TWIN` 与其他 V2 动作已明确列出；开启动作不等于开启执行。不要为通过检查而把图片处理权利 `RIGHTS_UNKNOWN` 改成已授权。

模型和编辑适配器在 image-options 文件中的相对路径，以该配置文件所在目录解析；正式 run/read_only/full-audit 三个入口使用相同解析规则。

## 独立 LaMa 权重

使用自己有权使用的本地 TorchScript 文件。安装命令先检查源 SHA256，再创建独立字节副本；不下载、不运行推理、不覆盖其他文件。目标已是同一 SHA 时返回 ALREADY_INSTALLED。

```powershell
.\run.cmd models install-lama --source C:\your-models\big-lama.pt --destination D:\GitHub\MyE-C-skill\automation\models\lama\big-lama.pt --sha256 你的64位SHA256 --bind-config D:\GitHub\MyE-C-skill\automation\local
```

本次本地补齐已安装一份独立权重并绑定其 SHA，未执行训练模型推理。图片 rights 保持 UNKNOWN；业务修复仍受原有权限、掩膜保护和质量门禁约束。权重不包含在 wheel 中。

## 旧水印模板

旧红色店铺文字模板现位于包内 `assets/watermarks/`，示例路径可正确定位，原始模板字节与来源说明 SHA 保留。它仅用于明确选择的 legacy 筛查路径，不作为 V2 语义分类依据。

## 部署审查

```powershell
.\run.cmd deploy review --install-root D:\GitHub\MyE-C-skill\automation --output .\data\deployment-review
```

该命令生成审查 JSON 和原有 Windows 审查辅助脚本，不创建用户、不改权限、不注册服务、不启动线上执行。后续仍复用 `mye_c_automation.executor.deployment_preflight`；跨账号权限证明和生产启用不能由 Fake 代替。

## 退出码与结果

命令成功通常退出 0；缺少配置或参数/文件错误退出 2。Fake、workflow 的业务结果必须另看 JSON 中的状态；不能只凭退出码 0 认定整件商品完成。真实验证步骤和授权边界见 `real-validation-proposal.md`。


## 本机密钥文件

当前用户提供的密钥保存在 `local/model-key.local.json`，已由 `*.local.json` 忽略，不随安装包分发。软件的模型客户端仍从 `VLM_API_KEY` 读取；在新的 PowerShell 窗口运行前显式加载本地文件：

```powershell
$env:VLM_API_KEY = (Get-Content -Raw .\local\model-key.local.json | ConvertFrom-Json).VLM_API_KEY
.\run.cmd configure check --directory .\local --shop 7 --pid 5094
```

该检查离线执行。请勿直接打印密钥变量或提交本地配置。执行真实任务仍需对应商品和动作的明确授权；本次 5094 只读任务已获授权，不包含上传或保存。
