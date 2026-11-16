"""Produce final evidence from observed runs; does not modify the source Skill."""
import ast,collections,hashlib,json,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT.parent/'aliexpress-product-image-audit'
REPORTS=ROOT/'reports'

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def write(name,text):(REPORTS/name).write_text(text,encoding='utf-8')

def main():
    baseline=read(REPORTS/'baseline-tests-status.json')
    isolation=read(REPORTS/'final-isolation/summary.json')
    regression=read(REPORTS/'final-isolation/regression/summary.json')
    old=read(REPORTS/'source-before.json')
    after={p.relative_to(SOURCE).as_posix():dict(sha256=digest(p),bytes=p.stat().st_size) for p in SOURCE.rglob('*') if p.is_file()}
    write('source-after.json',json.dumps(after,indent=2))
    differences=[p for p in sorted(old.keys()|after.keys()) if old.get(p)!=after.get(p)]
    before_git=read(REPORTS/'workspace-before.json')
    after_git={c:subprocess.check_output(['git',*c.split()],cwd=SOURCE).decode('utf-8',errors='replace') for c in before_git}
    write('workspace-after.json',json.dumps(after_git,ensure_ascii=False,indent=2))
    integrity=dict(files_before=len(old),files_after=len(after),bytes=sum(r['bytes'] for r in after.values()),changed=differences,
        head_unchanged=before_git['rev-parse HEAD']==after_git['rev-parse HEAD'],branch_unchanged=before_git['branch --show-current']==after_git['branch --show-current'],
        original_unstaged_diff_unchanged=before_git['diff']==after_git['diff'],staged_diff_unchanged=before_git['diff --cached']==after_git['diff --cached'])
    write('source-integrity.json',json.dumps(integrity,indent=2))
    ids=read(REPORTS/'final-isolation/regression/ids.json')['all'];baseline_ids=read(REPORTS/'baseline-test-ids.json')['all']
    inherited=[i for i in ids if not i.startswith(('test_independent_software.','test_packaged_configuration.'))]
    parity=dict(baseline_count=len(baseline_ids),inherited_count=len(inherited),new_count=len(ids)-len(inherited),exact_multiset=collections.Counter(baseline_ids)==collections.Counter(inherited))
    write('test-discovery-parity.json',json.dumps(parity,indent=2))
    # Verify original assertion expressions remain intact after import relocation.
    assertion_changes=[]
    def assertions(path):
        tree=ast.parse(path.read_text(encoding='utf-8-sig'))
        return collections.Counter(ast.dump(n,include_attributes=False).replace('mye_c_automation.','') for n in ast.walk(tree)
            if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr.startswith('assert'))
    for p in (SOURCE/'tests').glob('test_*.py'):
        if assertions(p)!=assertions(ROOT/'tests'/p.name):assertion_changes.append(p.name)
    write('test-assertion-parity.json',json.dumps(dict(changed_files=assertion_changes),indent=2))
    package=ROOT/'src/mye_c_automation'
    module_names=set(read(REPORTS/'dependency-audit.json')['modules'])
    imports=[];paths=[];injections=[];symlinks=[]
    for p in package.rglob('*'):
        if p.is_symlink():symlinks.append(str(p))
        if p.suffix!='.py':continue
        text=p.read_text(encoding='utf-8');tree=ast.parse(text)
        for n in ast.walk(tree):
            if isinstance(n,ast.ImportFrom) and n.level==0 and n.module and n.module.split('.')[0] in module_names:imports.append(dict(file=str(p),module=n.module))
            if isinstance(n,ast.Import):
                imports.extend(dict(file=str(p),module=a.name) for a in n.names if a.name.split('.')[0] in module_names)
        if 'sys.path.insert' in text:injections.append(str(p))
        if str(SOURCE) in text or '../aliexpress-product-image-audit' in text:paths.append(str(p))
    scan=dict(legacy_bare_imports=imports,old_runtime_paths=paths,sys_path_injections=injections,symlinks=symlinks,
        note='Namespaced dynamic task imports and explicitly configured image adapters remain intentional. Development extraction scripts and provenance documents may name the read-only source.')
    write('dependency-scan.json',json.dumps(scan,indent=2))
    provenance=read(REPORTS/'migration-provenance.json')
    for row in provenance:row['target_sha256']=digest(ROOT/row['target'])
    provenance.append(dict(source='references/SOP-商品标题重写.md',source_sha256=digest(SOURCE/'references/SOP-商品标题重写.md'),target='src/mye_c_automation/config/title-mappings.md',target_sha256=digest(package/'config/title-mappings.md'),method='Extract only program-parsed translation table; no Skill SOP loaded'))
    write('migration-provenance.json',json.dumps(provenance,ensure_ascii=False,indent=2))
    evidence=['baseline-tests-status.json','baseline-test-ids.json','final-isolation/summary.json','final-isolation/regression/summary.json','final-isolation/regression/ids.json','final-isolation/regression/source-binding.json','source-before.json','source-after.json','source-integrity.json','dependency-scan.json','test-discovery-parity.json','test-assertion-parity.json','migration-provenance.json']
    hashes={name:digest(REPORTS/name) for name in evidence}
    write('evidence-sha256.json',json.dumps(hashes,indent=2))
    source_ok=not differences and all(v for k,v in integrity.items() if k.endswith('unchanged'))
    scan_ok=not any(scan[k] for k in ('legacy_bare_imports','old_runtime_paths','sys_path_injections','symlinks'))
    passed=source_ok and scan_ok and isolation['passed'] and parity['exact_multiset'] and not assertion_changes and baseline['exit_code']==0 and regression['failures']==0 and regression['errors']==0 and regression['skipped']==0 and regression['source_unchanged']
    write('source-integrity.md',f'''# 原项目完整性

原 Skill 全目录 {len(old)} 个文件、{integrity['bytes']} 字节，任务前后逐文件 SHA256 / 大小对比：{'一致' if not differences else '存在变化'}。
HEAD、分支、用户原有未暂存差异和暂存差异：{json.dumps(integrity,ensure_ascii=False)}。

完整清单：`source-before.json` / `source-after.json`。原项目没有移动、删除或改写；本任务代码和证据仅新增于 automation。没有 git add、commit、push。其他 Skill 原有改动保持原样。
''')
    write('regression-test.md',f'''# 独立回归

原发现集 {parity['baseline_count']} 项，迁移后对应 {parity['inherited_count']} 项，多重集一致：{parity['exact_multiset']}；新增软件独立性测试 {parity['new_count']} 项。

隔离 wheel 的完整发现运行结果：`{json.dumps(regression,ensure_ascii=False)}`。

命令：新 venv 中 `python -B scripts/run_tests.py --output <isolated>/reports/regression`。全量日志、ID、源码绑定在 `final-isolation/regression/`；断言表达式比对在 `test-assertion-parity.json`。

初次完整迁移运行保留于 `first-regression/`（935 项，39 个错误，0 失败），暴露固定历史对照文件和测试临时目录遗漏、旧缓存路径；已修复测试资源定位，未降低业务规则或删改断言。新增场景先失败后通过记录：`demo-red.log` / `cli-green/`。旧归档 Fake 契约定向 20 项结果：`archived-green/`。

历史 931 项报告不是本软件验收。此次安装、CV、Fake 与完整回归均重新执行；真实模型和线上操作为 0。
''')
    fake={name:read_json_log(REPORTS/'isolation'/('fake-'+name+'.log')) for name in ('twin','frame','repair','keep')}
    write('independence-test.md',f'''# 独立性验证

独立目录：`{isolation['isolation_root']}`。
wheel SHA256：`{isolation['wheel_sha256']}`。

在新建 venv 内通过本地 wheelhouse 离线安装自身和依赖，安装日志 `final-isolation/install.log`。未使用 editable、旧项目 PYTHONPATH、软链接或旧目录资源。

对原 Skill 和 automation 开发源码目录安装进程级 Python audit hook；子 Python 进程继承同一保护。原 Skill 文件读取自检被拒绝 {isolation['expected_guard_probes']} 次；实际运行意外禁止访问数：{len(isolation['unexpected_forbidden_access'])}。网络连接和域名解析同样拒绝。

边界：这是继承到子进程的解释器文件访问隔离，不是 OS 容器或防恶意原生代码的安全沙箱；没有改动原目录 ACL 或名称。

帮助、doctor、四个 Fake 场景和完整回归结果均保留在 `final-isolation/`。Fake 结果：

| 场景 | 状态 | Fake 保存 | Fake 上传 | 独立回读 |
|---|---|---:|---:|---:|
'''+ '\n'.join(f"| {name} | {v['status']} | {v['saves']} | {v['uploads']} | {v['independent_readbacks']} |" for name,v in fake.items())+
        '\n\nJob、图片缓存、账本、计划、日志及回读记录均落在新软件独立数据根；文件 SHA 清单在 `final-isolation/summary.json`。原始目录访问不是依赖。\n')
    write('feature-parity.md','''# V2 功能对应与状态

| 基准能力 | 新软件模块 | 验证状态 / 测试 |
|---|---|---|
| DeepSeek 单模型、禁用 MiMo 和静默回退 | ai_judge / model_config | IMPLEMENTED, UNIT_TESTED, FAKE_VERIFIED；test_v2_deepseek_only, test_current_model_selection |
| 置信度 RECORD_ONLY、usage 缺失为 null | image_action_decision / budget_manager | IMPLEMENTED, FAKE_VERIFIED；test_v2_confidence_record_only |
| 全图审核与 SHA 多 URL 归组 | full_product_audit / image_content_plan | IMPLEMENTED, FAKE_VERIFIED；test_v2_reusable_rules |
| 正文图片、text-image 边界、shopFooter 和正文样式保护 | description_images | IMPLEMENTED, FAKE_VERIFIED；test_description_image_edits, test_v2_reusable_rules |
| 同照片 SIFT / RANSAC / 覆盖率 / 中心稠密像素证明 | visual_versions | IMPLEMENTED, LOCAL_CV_VERIFIED；test_visual_versions 的原图、压缩缩放、不同姿势案例 |
| 干净 KEEP 同照片优先 REPLACE_TWIN、零上传 | v2_remediation / existing executor | IMPLEMENTED, FAKE_VERIFIED；test_visual_versions.VersionWorkflowTests，独立 CLI twin |
| 无 twin 大边框删除 / 小覆盖字局部修复 | image_action_decision / image_repairs_v2 | IMPLEMENTED, FAKE_VERIFIED；独立 frame / repair、test_v2_reusable_rules |
| 未知文字保留、厂家包装产品署名保护 | image_action_decision | IMPLEMENTED, FAKE_VERIFIED；test_v2_text_color_policy, test_v2_full_workflow |
| 主图、详情、正文、SKU 池、真实 SKU 行统一同步 | v2_remediation / sku_assignment | IMPLEMENTED, FAKE_VERIFIED；test_visual_versions, test_v2_two_sku_images |
| 两张无盒不同 SHA 图绑定两个现有规格 | sku_assignment | IMPLEMENTED, FAKE_VERIFIED；test_v2_two_sku_images |
| 受限计划、一次保存、超时先回读、禁止盲重发 | plan_compiler / executor.local | IMPLEMENTED, FAKE_VERIFIED；test_v2_workflow, test_v2_full_workflow |
| 独立引用和图片字节回读、非图片字段精确保留 | v2_remediation.verify_content | IMPLEMENTED, FAKE_VERIFIED；包括漂移、失败和响应丢失对照 |
| LaMa 两种 TorchScript 契约和精确 mask | image_repairs_v2 | IMPLEMENTED, UNIT_TESTED；合成 TorchScript；训练权重未复制 |
| 可配置外部图像编辑适配器 | image_repairs_v2 / v2_remediation | IMPLEMENTED；真实服务 NOT_RUN |
| 独立安装、资源、CLI、Job/缓存/账本/日志 | pyproject / cli / paths / resources | IMPLEMENTED, FAKE_VERIFIED；隔离 wheel 完整回归 |

所有 REAL_MODEL_VERIFIED、REAL_READONLY_VERIFIED、REAL_WRITE_VERIFIED 均 NOT_RUN；PRODUCTION_READY 不作声明。SKU 当前每行仍只有一个 skuImageUrl，没有虚构多图接口。图片外业务规则未重新设计。
''')
    write('migration-acceptance.md',f'''# 独立化最终验收

状态：{'COMPLETE（本地独立软件交付）' if passed else 'INCOMPLETE（详见 JSON 差异）'}。
基准 HEAD：68e168f1a08c6338cb0964dffbd021bb5e484556；证据日期：2026-11-16。

automation 已具有可安装 src 包、CLI/JSON、独立依赖、配置、Prompt、Schema、测试和运行数据。原 V2 的 runner / 客户端 / 计划编译器 / 执行器 / 账本 / 回读器按调用链复用。

迁移前原发现集：{baseline['tests']} 项，失败 {baseline['failures']}、错误 {baseline['errors']}、跳过 {baseline['skipped']}。隔离 wheel 回归：{regression['tests']} 项，失败 {regression['failures']}、错误 {regression['errors']}、跳过 {regression['skipped']}。原测试发现多重集保留：{parity['exact_multiset']}；原 Skill {len(old)} 个文件完整性：{source_ok}；运行依赖静态扫描：{scan_ok}。

四个完整 Fake 场景见 independence-test.md：同照片优先替换零上传、无 twin 边框删除零上传、局部修复一次上传、KEEP 零保存。均使用新 Job、Mock DeepSeek、独立 Fake reader 和真实迁移生产执行链。原始观察与最终策略动作分别归档。

IMPLEMENTED / UNIT_TESTED / FAKE_VERIFIED / LOCAL_CV_VERIFIED 如 feature-parity.md 所列。真实语义模型准确率、真实模型请求、线上读取/上传/保存/部署全部 NOT_RUN；不能标记 PRODUCTION_READY。外部编辑真实服务、训练权重分发和平台单 SKU 多图能力没有新增验证，保留为未来独立事项。

只迁移必要固定夹具：旧验收的六张原图、派生视觉证据、三份输入元数据及一份历史结果对照；重建独立夹具 seal，不改写原 433 文件 seal。未复制旧活动 Job、授权、数据库或缓存。原有固定 V2 图像/人工标签保留来源及 SHA；不得把历史准确率解释为新版真实验收。

软件分发包：dist/mye_c_automation-0.1.0-py3-none-any.whl。使用说明：README.md。完整证据 SHA：evidence-sha256.json。详细原始清单：asset-inventory.json；源→目标及内容变化：migration-provenance.json。

隔离边界明确：wheel 新 venv、原 Skill 和开发源码的 Python 文件读取被阻断；不是 OS 容器。没有改原目录权限。未进行 git add、commit、push。
''')
    write('acceptance-status.json',json.dumps(dict(complete=passed,source_integrity=source_ok,dependency_scan=scan_ok,test_parity=parity,assertion_changes=assertion_changes,real_model='NOT_RUN',real_readonly='NOT_RUN',real_write='NOT_RUN',production_ready=False),indent=2))
    print(json.dumps(dict(complete=passed,integrity=integrity,parity=parity,assertion_changes=assertion_changes)))
    return 0 if passed else 1

def read_json_log(path):
    return json.loads(path.read_text(encoding='utf-8').strip().splitlines()[-1])

if __name__=='__main__':raise SystemExit(main())
