"""Verify follow-up evidence and source preservation, leaving extraction reports intact."""
import ast,collections,hashlib,json,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/readiness-20261116'
SOURCE=ROOT.parent/'aliexpress-product-image-audit'

def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def main():
    isolated=read(OUT/'isolation/summary.json');tests=read(OUT/'isolation/regression/summary.json')
    baseline_ids=read(ROOT/'reports/final-isolation/regression/ids.json')['all']
    current_ids=read(OUT/'isolation/regression/ids.json')['all']
    inherited=[x for x in current_ids if not x.startswith('test_runtime_readiness.')]
    parity=dict(previous=len(baseline_ids),inherited=len(inherited),new=len(current_ids)-len(inherited),exact_multiset=collections.Counter(baseline_ids)==collections.Counter(inherited))
    before=read(ROOT/'reports/source-after.json')
    after={p.relative_to(SOURCE).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size) for p in SOURCE.rglob('*') if p.is_file()}
    changed=[p for p in sorted(before.keys()|after.keys()) if before.get(p)!=after.get(p)]
    (OUT/'original-source-after.json').write_text(json.dumps(after,indent=2),encoding='utf-8')
    git_before=read(OUT/'git-before.json')
    git_after={c:subprocess.check_output(['git',*c.split()],cwd=ROOT).decode('utf-8',errors='replace') for c in git_before}
    (OUT/'git-after.json').write_text(json.dumps(git_after,ensure_ascii=False,indent=2),encoding='utf-8')
    protected_git=all(git_before[c]==git_after[c] for c in ('rev-parse HEAD','diff','diff --cached'))
    # All previous assertion expressions remain unchanged. Resource/schema changes
    # must never be justified by removing a regression assertion.
    def assertions(path):
        return collections.Counter(ast.dump(n,include_attributes=False).replace('mye_c_automation.','') for n in ast.walk(ast.parse(path.read_text(encoding='utf-8-sig')))
            if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr.startswith('assert'))
    assert_changes=[p.name for p in (SOURCE/'tests').glob('test_*.py') if assertions(p)!=assertions(ROOT/'tests'/p.name)]
    source_before=read(OUT/'before.json');source_after={name:sha(ROOT/name) for name in source_before if (ROOT/name).is_file()}
    modified=[name for name in source_before if source_before[name]!=source_after.get(name)]
    local_model=ROOT/'models/lama/big-lama.pt';model_info=read(ROOT/'models/resources.json')['lama']
    model_ok=local_model.is_file() and sha(local_model)==model_info['baseline_sha256']
    resources=read(OUT/'resource-provenance.json')
    resources_ok=all(sha(ROOT/r['target'])==r['sha256'] for r in resources)
    local_check=read(OUT/'local-readiness.json')
    result=dict(local_complete=isolated['passed'] and tests['failures']==0 and tests['errors']==0 and tests['skipped']==0 and tests['source_unchanged'] and parity['exact_multiset'] and not changed and protected_git and not assert_changes and model_ok and resources_ok,
        overall_status='LOCAL_VERIFIED_REAL_PENDING',tests=tests,discovery=parity,original_files=len(after),original_changed=changed,
        original_assertion_changes=assert_changes,user_git_diff_preserved=protected_git,independent_model_bytes_verified=model_ok,packaged_resource_bytes_verified=resources_ok,
        modified_previous_automation_files=modified,configuration_blockers=local_check['blockers'],
        real_model='NOT_RUN',real_readonly='NOT_RUN',real_write='NOT_RUN',trained_lama_inference='NOT_RUN',external_edit_service='NOT_CONFIGURED',production_ready=False)
    (OUT/'acceptance.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    text=f'''# 0.2.0 本地功能补齐与验证

当前状态：LOCAL_VERIFIED_REAL_PENDING。本地实现验收：{result['local_complete']}。
保留基准 HEAD 68e168f，不暂存、不提交、不推送，原 Skill 只读。

## 已完成

| 缺项 | 当前实现 | 证据 |
|---|---|---|
| REPLACE_TWIN 示例缺少权限 | 示例补齐，enabled 仍 false；正式规划/执行 Fake 证明确实替换零上传 | final-targeted/tests.log、完整回归 |
| 旧模板示例悬空 | 包内模板/来源 JSON，正确相对路径，SHA 一致；V2 不借此做语义分类 | resource-provenance.json、wheel-content.json |
| 无配置初始化和完整离线检查 | configure init/check、doctor --config-dir；保留已有文件、无网络、密钥仅报告存在性 | 配置/CLI新增测试、isolation/configure-*.log |
| LaMa 独立资源未配置 | 独立复制并固定 SHA，配置只引用新目录；权利仍 UNKNOWN | local-model-install.json、local-readiness.json |
| 配置路径依赖运行目录 | 正式三个 V2 入口都按 image-options 所在目录解析模型/适配器相对路径 | 正式 full-audit 入口新增测试、原工作流回归 |
| 部署辅助工具遗漏 | 迁移原 Windows 审查 helper，deploy review；无账号/权限/服务变更 | deployment-review.json、isolation/deployment-review.log |
| Windows 运行入口 | run.cmd、scripts/Test-Automation.ps1；委托既有 CLI 和测试入口 | 手动帮助/PowerShell语法核对、使用说明 |

## 验证结果

完整独立 wheel 回归 {tests['tests']} 项，失败 {tests['failures']}、错误 {tests['errors']}、跳过 {tests['skipped']}、网络尝试 {tests['network_attempts']}。
上一阶段 {parity['previous']} 项发现多重集保留：{parity['exact_multiset']}，新增 {parity['new']} 项。原测试断言变化：{assert_changes}。
隔离安装、配置初始化、缺配置正确退出 2、部署审查、四个完整 Fake 场景均在原 Skill 和开发源码目录被 Python 访问保护拒绝的环境中验证；不是 OS 容器。wheel：`{isolated['wheel_sha256']}`；本轮 wheel 在测试期间未改变：{isolated.get('wheel_unchanged')}。
原 Skill {len(after)} 个文件 SHA 对比变化：{changed}。用户其他 Git 差异保留：{protected_git}。原迁移报告不改写；本轮独立证据保存在本目录。

## 尚不能宣布完成的真实验收

本地缺项：{local_check['blockers']}。后台凭据请仅填写本地 local/site.local.json，密钥在本地设置 VLM_API_KEY，不要发到聊天。
真实后台读取、DeepSeek 请求、线上上传/保存和训练 LaMa 推理均 NOT_RUN。A 只读提案和 B 写入提案见 docs/real-validation-proposal.md：仍需要独立指定店铺/商品与授权，不复用旧 Job。未配置的外部图像编辑服务不假定可用，不外部找图，不宣称生产就绪。
图形界面是上一条建议中的后续增强；本轮按优先顺序完成 CLI 与运行配套，未声称提供 GUI 或长期后台服务。用户若选择本轮包含界面，将继续独立实施。

## 运行

```powershell
cd D:\\GitHub\\MyE-C-skill\\automation
.\\run.cmd configure check
.\\run.cmd doctor --config-dir .\\local
.\\run.cmd fake --scenario twin
```

完整配置说明：docs/configuration-and-readiness.md。所有结果原始 JSON 在本目录，SHA 清单见 evidence-sha256.json。
'''
    (OUT/'acceptance.md').write_text(text,encoding='utf-8')
    hashes={p.relative_to(OUT).as_posix():sha(p) for p in OUT.rglob('*') if p.is_file() and p.name not in {'evidence-sha256.json','final-console.log'} and 'data' not in p.relative_to(OUT).parts}
    (OUT/'evidence-sha256.json').write_text(json.dumps(hashes,indent=2),encoding='utf-8')
    print(json.dumps(result))
    return 0 if result['local_complete'] else 1

if __name__=='__main__':raise SystemExit(main())
