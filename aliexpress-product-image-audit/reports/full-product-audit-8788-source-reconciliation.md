# 审核源码清单与GitHub源码哈希差异核对

用户指出的原始SHA256差异属实。原清单计算Windows本地文件原始字节，Git提交时按core.autocrlf=true将CRLF转换为LF。原始字节不同，不能称为逐字节一致。此前交付没有区分本地原始哈希和Git仓库哈希，这是证据说明缺陷。
固定核对main提交：`37c88ee9457a1a777643e60bed17c85609a60343`。Git文件字节使用git cat-file读取未经过滤的仓库blob。原清单保留原样，没有替换历史哈希来制造一致。

## 用户指出的7个文件

| 文件 | 原始字节对比 | 统一为LF后 |
|---|---|---|
| scripts/full_product_audit.py | 一致 | 完全一致 |
| scripts/full_audit_recovery.py | 一致 | 完全一致 |
| scripts/ai_judge/watermark.py | 不一致，仅CRLF/LF差异 | 完全一致 |
| scripts/ai_judge/product_identity.py | 不一致，仅CRLF/LF差异 | 完全一致 |
| scripts/ai_judge/schemas.py | 不一致，仅CRLF/LF差异 | 完全一致 |
| scripts/ai_judge/client.py | 不一致，仅CRLF/LF差异 | 完全一致 |
| scripts/evidence_builder.py | 不一致，仅CRLF/LF差异 | 完全一致 |

## 全部233个清单文件

- 78个：原始字节完全一致。
- 148个：仅CRLF→LF差异。
- 7个：换行及文件末尾空行清理。
- 233个Python文件的语法树均一致，未发现无法解释的源码内容变化。

末尾空行变化发生在提交前清理空白时，是实际的发布字节变化，不能隐藏为“原始文件完全一致”：

- scripts/executor/authorization.py
- scripts/executor/deployment_preflight.py
- scripts/executor/ipc.py
- scripts/executor/local.py
- tests/test_auto_box_workflow.py
- tests/test_business_matrix.py
- tests/test_deployment_preflight.py

这7个文件的历史字节形式通过只改变换行/末尾空行的候选重建，并以原清单SHA256验证匹配。重建只用于解释差异，不冒充当时保存的原始源码副本，不回填历史审核证据。

## 如何复核

同名JSON给出audit_original_sha256（审核原始字节）、verified_main_blob_sha256（Git仓库原始字节）、verified_main_lf_sha256（统一LF）及difference_kind。下载GitHub文件直接计算SHA256，应对照verified_main_blob_sha256。
原full-product-audit-8788-source-manifest.json仍是历史Windows原始字节清单，不能直接要求GitHub的LF文件匹配它。

## 证明范围

本核对证明所记录源码快照与指定main提交之间的代码文本/语法关系；不追溯证明历史进程每个已加载模块、依赖版本或每次请求的运行时状态。旧运行没有完整的逐进程模块哈希留存，不能事后补成已验证。
准确结论：所列7个重点文件统一换行后完全相同；全清单未发现函数或提示词源码内容变化，但存在发布格式差异与运行时溯源证据限制。没有重新调用模型、改变历史判断、调整置信度或写入商品。
