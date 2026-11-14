# token-opt-v2 Phase 0 基线报告

日期：2026-11-12

## 已验证

使用现有 `../ae-img-audit/.venv/Scripts/python.exe`，设置 `PYTHONPATH=scripts`，执行 `python -m unittest discover -s tests -q`：12 项测试全部通过（0.045 秒）。系统 Python 缺少 cv2，不能作为本项目测试环境。

`baseline-v1.zip` 由仓库 HEAD 的本技能跟踪文件生成，保留 v1 回滚来源；未打包本地凭证、缓存或商品工作数据。原有 v1 脚本未修改。未调用真实商品审核或写站接口。

## 依赖观察

`audit_one.py` 依赖 OpenCV、NumPy，入口仍为 v1，只读预审固定写入按 PID 的工作目录。`token_opt_plan.py` 严格接受 v1 计划，不能直接替换 schema 常量，否则破坏 v1。v2 应增量增加独立控制层和计划解析器，并在完成 job 隔离后接入现有审核函数。

## 尚未满足的 Phase 0 验收

缺少 20–30 件代表性商品运行数据、人工标注水印样本及对应双模型结果。本次未执行生产采样，不能声称质量、性能或漏检率验收通过。

## 后续范围

按原实施方案依次实施 Phase 1–4，每阶段独立测试和报告。Phase 5 仅可添加 Shadow Mode，不能启用未经回归验证的分级 OCR 或单模型首判。独立执行器在部署独立账户、凭证 ACL 及受限通信之前，不可声称实现强隔离，默认必须拒绝写入。
