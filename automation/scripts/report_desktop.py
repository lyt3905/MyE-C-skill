"""Desktop-stage acceptance from fresh isolated tests; does not imply live readiness."""
import collections,hashlib,json,subprocess,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/ui-20261116'
SOURCE=ROOT.parent/'aliexpress-product-image-audit'
def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def main():
    isolated=read(OUT/'isolation/summary.json');test=read(OUT/'isolation/regression/summary.json')
    previous=read(ROOT/'reports/readiness-20261116/isolation/regression/ids.json')['all']
    ids=read(OUT/'isolation/regression/ids.json')['all'];inherited=[i for i in ids if not i.startswith('test_desktop_interface.')]
    parity=collections.Counter(previous)==collections.Counter(inherited)
    old=read(ROOT/'reports/readiness-20261116/original-source-after.json')
    new={p.relative_to(SOURCE).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size) for p in SOURCE.rglob('*') if p.is_file()}
    changed=[p for p in sorted(old.keys()|new.keys()) if old.get(p)!=new.get(p)]
    (OUT/'original-source-after.json').write_text(json.dumps(new,indent=2),encoding='utf-8')
    git_before=read(ROOT/'reports/readiness-20261116/git-before.json')
    git_after={c:subprocess.check_output(['git',*c.split()],cwd=ROOT).decode('utf-8',errors='replace') for c in git_before}
    git_ok=all(git_before[c]==git_after[c] for c in ('rev-parse HEAD','diff','diff --cached'))
    (OUT/'git-after.json').write_text(json.dumps(git_after,ensure_ascii=False,indent=2),encoding='utf-8')
    wheel=ROOT/'dist/mye_c_automation-0.3.0-py3-none-any.whl'
    with zipfile.ZipFile(wheel) as archive:
        differences=[n for n in archive.namelist() if n.startswith('mye_c_automation/') and not n.endswith('/') and hashlib.sha256((ROOT/'src'/n).read_bytes()).digest()!=hashlib.sha256(archive.read(n)).digest()]
    native=read(OUT/'native-ui-status.json')
    from mye_c_automation.configuration import check_configuration
    config=check_configuration(ROOT/'local')
    (OUT/'local-readiness.json').write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
    verified=isolated['passed'] and test['failures']==test['errors']==test['skipped']==0 and test['source_unchanged'] and parity and not changed and not differences and git_ok
    result=dict(status='LOCAL_AUTOMATED_VERIFIED_VISUAL_AND_REAL_PENDING',local_automated_verified=verified,
        tests=test,previous_tests=len(previous),inherited_tests=len(inherited),new_tests=len(ids)-len(inherited),discovery_exact=parity,
        original_files=len(new),original_changed=changed,user_git_diff_preserved=git_ok,wheel_sha256=sha(wheel),wheel_source_differences=differences,
        native_visual_check=native['native_visual_check'],config_blockers=config['blockers'],real_model='NOT_RUN',real_readonly='NOT_RUN',real_write='NOT_RUN',
        trained_lama_inference='NOT_RUN',external_edit_service='NOT_CONFIGURED',production_ready=False)
    (OUT/'acceptance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'acceptance.md').write_text(f'''# 0.3.0 本地桌面界面

本地自动化验证：{verified}。全目标仍为待完成，不能由此宣称真实或生产验收通过。

新增 ui CLI 和 gui.cmd，配置页、离线检查、后台 Fake 进度、Job 历史及原图/候选对比均复用既有 CLI/Job/计划/账本。后台账号和密码只保存本地连接配置，API key 只留会话，不改自动化授权。保存前检查文件版本；界面不提供真实商品执行或自动上线按钮。

## 证据

- 独立 wheel 完整回归 {test['tests']} 项，失败/错误/跳过均 0，网络尝试 {test['network_attempts']}，源码绑定不变 {test['source_unchanged']}。
- 原 {len(previous)} 项发现多重集一致 {parity}；新增 {len(ids)-len(inherited)} 项覆盖 CLI 委托、配置冲突、密钥不落盘、未知状态、任务和图片字节绑定、真实 Tk 控件及 Fake 子进程完成/图片显示。
- 独立 venv 安装后原 Skill 和开发源码目录的 Python 文件访问被阻断；完整结果在 isolation/，不是 OS 容器。
- 当前源文件与 wheel 文件逐项差异 {differences}；wheel SHA256 `{sha(wheel)}`。
- 原 Skill {len(new)} 个文件 SHA 变化 {changed}，原用户 Git 差异保持 {git_ok}。
- 保留的局部修复演示：retained-demo.json；数据在 data/ui-review-20261116。Mock 模型、Fake 上传保存和独立读取，不是线上任务。

## 仍需用户参与

原生窗口已启动，但 computer-use 截图返回 Windows 锁屏，未点击任何界面，未尝试解锁/绕过。视觉与实际鼠标检查状态 `{native['native_visual_check']}`；Tk 自动化控件测试通过不能冒充视觉验收。用户解锁后可双击 gui.cmd 检查三个页签。

配置当前缺项 {config['blockers']}；真实后台读取、模型调用、商品写入、训练 LaMa 推理均 NOT_RUN，外部图像编辑服务未配置。仍按 docs/real-validation-proposal.md 分别授权；旧 Job 不复用。图形界面的开发完成不消除这些外部条件。

## 使用

双击 `D:\\GitHub\\MyE-C-skill\\automation\\gui.cmd` 或在本目录执行 `.\\run.cmd ui`。已安装 wheel 时 `myec-automation ui`，可显式指定 --config-dir / --data-root。操作说明：docs/desktop-interface.md。
''',encoding='utf-8')
    manifest={p.relative_to(OUT).as_posix():sha(p) for p in OUT.rglob('*') if p.is_file() and p.name not in {'evidence-sha256.json','final-console.log'} and 'data' not in p.relative_to(OUT).parts}
    (OUT/'evidence-sha256.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
    return 0 if verified else 1

if __name__=='__main__':raise SystemExit(main())
