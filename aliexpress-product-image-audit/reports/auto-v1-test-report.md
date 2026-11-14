# 自动化测试报告

Ran 300 tests in 49.648s，OK；去重260项。Windows Python 3.12；执行命令scripts/run_auto_tests.ps1。原始日志auto-v1-current-regression.log，完整测试ID见auto-v1-test-inventory.json。

保留原有回归；新增标准Workflow孪生、裁切、SKU、标题四条闭环，以及试擦、官方池、盒照补边、生成图SKU完整Fake流程。E01–E35证据与组件/流程范围见auto-v1-SOP-coverage-matrix.md。包含1/3/10件批次、跨店铺串行、未知写入恢复及熔断、内容失败优先于翻译待重试、真实双进程上传节流、预算原子预留、证据哈希、Schema、受控回滚和AUTO_CONDITIONAL验证过程。

Site/模型语义采用Fake或Mock，图像处理和Windows进程/文件锁代码真实执行。未进行生产试写；真实OCR/GLM/Kimi质量、站点只读Canary、真实上传/保存/翻译/回滚未验证。Fake通过不表示生产通过。

交付包隔离回归日志为auto-v1-delivery-regression.log；最终压缩包逐文件哈希见交付目录sync-manifest.json。依赖使用现有已安装环境，全新机器安装未验证。

最终交付验收：当前源码完整回归300次/49.648秒/OK；同版本归档解压独立目录完整回归300次/48.809秒/OK，260个唯一测试。封存期间代码/JSON配置/PowerShell脚本SHA与已测试归档逐项一致。外部未验证项目仍按清单披露。
