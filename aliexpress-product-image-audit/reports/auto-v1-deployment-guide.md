# 部署指南（本地Fake验收版本）

工作目录：D:\GitHub\MyE-C-skill\aliexpress-product-image-audit。
现有可用测试解释器：..\ae-img-audit\.venv\Scripts\python.exe（Windows Python 3.12）。

```powershell
$env:PYTHONPATH='scripts'
..\ae-img-audit\.venv\Scripts\python.exe -m unittest discover -s tests -v
$env:AE_READONLY_SITE_CFG=(Resolve-Path .\local\site.json).Path
..\ae-img-audit\.venv\Scripts\python.exe scripts\workflow_runner.py run --pid 4758 --shop 7 --mode audit --root .\work\v2
..\ae-img-audit\.venv\Scripts\python.exe scripts\workflow_runner.py run --pid 4758 --shop 7 --mode dry_run --site-config .\local\site.json --root .\work\v2
```

模型凭证通过 VLM_API_KEY、VLM_BASE 本地配置，站点配置不入库；不要将这些值粘贴到报告。需要 Pillow/numpy/OpenCV/RapidOCR 与可用的模型网关。

自动执行示例（仅在最终验收与真实只读 Canary 通过后由用户启用）：
```powershell
# 从 scripts/config/automation.v1.example.json 复制并检查本地白名单，保存为 local/automation.v1.json。
..\ae-img-audit\.venv\Scripts\python.exe scripts\workflow_runner.py run --pid 4758 --shop 7 --mode auto_apply --automation-config .\local\automation.v1.json --site-config .\local\site.json --root .\work\v2
..\ae-img-audit\.venv\Scripts\python.exe scripts\workflow_runner.py run --batch '4758,4759' --shop 7 --mode auto_apply --automation-config .\local\automation.v1.json --site-config .\local\site.json --root .\work\v2
..\ae-img-audit\.venv\Scripts\python.exe scripts\workflow_runner.py status --job JOB_xxx --root .\work\v2
..\ae-img-audit\.venv\Scripts\python.exe scripts\workflow_runner.py report --job JOB_xxx --root .\work\v2
```

这些生产命令本轮均未执行。当前剩余风险见 auto-v1-implementation.md，不能将当前测试数视为全量验收完成。

只读失败恢复：
```powershell
..\ae-img-audit\.venv\Scripts\python.exe scripts\workflow_runner.py recover-readback --job JOB_xxx --site-config .\local\site.json --root .\work\v2
```
MATCHED 表示读回匹配保存前的期望快照；仍须内容复检。NOT_OBSERVED不能证明未来不会落库，DRIFT也不能猜测覆盖；这些情况均不允许重发save。

可选本地图池配置：automation本地配置增加 local_pool_index，路径相对该配置文件。索引包含 schema=official-image-pool/v1、items，每项包含 file、sha256、official_source=true、source_url、model、packaging_type（BOX/FIGURE/MIXED）。实际使用前仍需独立同款/干净度/保护元素复检。

独立恢复命令：
```powershell
..\ae-img-audit\.venv\Scripts\python.exe scripts\workflow_runner.py verify-saved --job JOB_xxx --site-config .\local\site.json --root .\work\v2
..\ae-img-audit\.venv\Scripts\python.exe scripts\workflow_runner.py retry-translation --job JOB_xxx --site-config .\local\site.json --automation-config .\local\automation.v1.json --root .\work\v2
```
verify-saved不写站；retry-translation只调翻译接口，校验原保存快照，不重新save。翻译尝试初次与重试合计最多2次；不要删translation_retry或预算数据库绕过限制。

依赖与一键测试：
```powershell
# 新建环境时先 python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-auto.txt -r requirements-dev.txt
.\scripts\run_auto_tests.ps1
```
脚本优先当前.venv，否则使用相邻ae-img-audit现有.venv；可用 -Python 显式指定。JSON Schema位于scripts/config/schemas，必须同时通过Python业务验证，不能仅凭结构Schema通过就写站。

模板配置：run支持 --template-config .\local\template_config.json。参照scripts/config/template_config.example.json配置真实模板；只有明确无适用模板的Shop才能放入no_applicable_shop_ids，必需模板缺失会阻断内容通过。

BOX_NORMALIZE为低分辨率盒照的独立动作权限，旧配置缺省关闭，示例为false；开启后仍需盒照/型号/清洁度观察及生成图独立复检。原始小图证据仍明确记录，不把放大等同画质合格。

全局上传速率：同一部署所有账号/Job使用local/global_upload_rate.sqlite，上传完成后至少0.5秒再开始下一次上传；不要为每账号复制独立代码目录或删除账本规避节流。SQLite锁超时/数据库错误会终止本次上传流程，不降级绕过。
