# 正本同步与回滚
正本D:/GitHub/MyE-C-skill/aliexpress-product-image-audit；../ae-img-audit是包含巨大旧脚本/环境/数据运行目录。本轮只借其.venv测试，没有覆盖运行目录，没有覆盖旧zip。
交付同步包应仅包含正本scripts/tests/reports/templates/config相关小文件及SHA256清单；不包含work、.venv、凭证或旧运行数据。用户审查后先备份目标同名文件，再按清单逐文件部署；不可整目录覆盖。
回滚恢复同名文件备份；保留Job证据和local_execution.json执行记录，不可删除记录后重试已不确定写入。
