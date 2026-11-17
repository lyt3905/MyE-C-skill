# 独立性验证

独立目录：`C:\Users\shana\AppData\Local\Temp\myec-independent-3z3ynohn`。
wheel SHA256：`15f3351a65e804cdac10becec9b8f41bb1eb24b606bd43ffa34145ec9d0d00ae`。

在新建 venv 内通过本地 wheelhouse 离线安装自身和依赖，安装日志 `final-isolation/install.log`。未使用 editable、旧项目 PYTHONPATH、软链接或旧目录资源。

对原 Skill 和 automation 开发源码目录安装进程级 Python audit hook；子 Python 进程继承同一保护。原 Skill 文件读取自检被拒绝 1 次；实际运行意外禁止访问数：0。网络连接和域名解析同样拒绝。

边界：这是继承到子进程的解释器文件访问隔离，不是 OS 容器或防恶意原生代码的安全沙箱；没有改动原目录 ACL 或名称。

帮助、doctor、四个 Fake 场景和完整回归结果均保留在 `final-isolation/`。Fake 结果：

| 场景 | 状态 | Fake 保存 | Fake 上传 | 独立回读 |
|---|---|---:|---:|---:|
| twin | AUTO_VERIFIED | 1 | 0 | 3 |
| frame | AUTO_VERIFIED | 1 | 0 | 3 |
| repair | AUTO_VERIFIED | 1 | 1 | 3 |
| keep | AUTO_VERIFIED | 0 | 0 | 0 |

Job、图片缓存、账本、计划、日志及回读记录均落在新软件独立数据根；文件 SHA 清单在 `final-isolation/summary.json`。原始目录访问不是依赖。
