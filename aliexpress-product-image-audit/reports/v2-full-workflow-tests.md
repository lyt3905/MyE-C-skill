# V2完整测试与证据

本轮基于756873e的现有V2定点修复；831项完整回归通过（失败/错误/跳过0），新增26项。标准测试入口退出0、网络尝试0、测试前后297份源码/配置/Prompt绑定一致。22个独立保留Fake场景、1个正式CLI完整Fake任务及2个本地OpenCV/真实训练LaMa的Fake工作流已完成。新增真实语义模型调用、线上读取/上传/保存均0；不add/commit/push。

运行ID：75723c6ff2bb4b358d6b15953ebabd16；耗时647.094秒。标准命令scripts/run_auto_tests.ps1 -TestHarness 本轮work/run_offline_tests.py -LogPath reports/v2-full-workflow-full-tests.log，退出码0。原805项保留，新增26项；没有跳过或删除。红→绿日志位于本轮work目录task-bc-red.log、task-efi-red.log、apply-cli-red.log及后续green/targeted日志，初次依赖路径/归档脚本错误也保留，不计作成功测试。

| 场景 | 新Job | 最终状态 | 模拟上传/保存 |
|---|---|---|---|
| normal_clean | JOB_633ae1cec6dc49dfbe832a62c2175a7a | PARTIALLY_AUTO_FIXED | 0/1 |
| store_watermark | JOB_8835cd3925044209a566669bb4c47aa9 | PARTIALLY_AUTO_FIXED | 1/1 |
| faint_watermark | JOB_432ced5336ba4ee1beb71da641b64c10 | PARTIALLY_AUTO_FIXED | 1/1 |
| with_retail_box | JOB_448bc328f01a4913b3b1fe2653a83284 | AUTO_VERIFIED | 0/1 |
| without_retail_box | JOB_774b03e32534403a876abe1fe7cec704 | PARTIALLY_AUTO_FIXED | 0/1 |
| multi_position_reference | JOB_0e827110850b4d179f9570add8d47c17 | PARTIALLY_AUTO_FIXED | 1/1 |
| duplicate_content | JOB_d43998fee02843b491cbdf03f4ed4281 | PARTIALLY_AUTO_FIXED | 0/1 |
| edit_success | JOB_97e56e7678964872abc73336cea0e51f | PARTIALLY_AUTO_FIXED | 1/1 |
| unknown_edit_usage | JOB_7cc3de91120d4e13b6219b8ec7c1374d | PARTIALLY_AUTO_FIXED | 1/1 |
| upload_failure | JOB_2341a5c866e34058bf91b6bd74be14f3 | APPLY_UNKNOWN | 1/0 |
| save_timeout | JOB_0e20cfa6d89141d2a6b7f175c44e526b | APPLY_UNKNOWN | 1/1 |
| save_applied_response_lost | JOB_1bf7e66b51ee450192dbdc6f53526b21 | APPLY_UNKNOWN | 1/1 |
| description_changed | JOB_bdee1afa3f004d7fad74a64b4a24e119 | APPLY_UNKNOWN | 1/1 |
| sku_changed | JOB_375606cb07e14f6582f6c3255d830810 | APPLY_UNKNOWN | 1/1 |
| retained_bytes_changed | JOB_70f2f37bc6574f0d84161bc751d69e71 | REVIEW_REQUIRED | 0/1 |
| decorated_composite | JOB_a30c4e1cc0684244809b0bf24e7f1415 | PARTIALLY_AUTO_FIXED | 0/1 |
| dual_conflict | JOB_8278e4178d3e4fe19996248eceb6222e | REVIEW_REQUIRED | 0/0 |
| low_confidence | JOB_bf14704824034e67aaec5000c2b70089 | REVIEW_REQUIRED | 0/0 |
| local_failure_to_editor | JOB_718d05a461554e3480bce394481b4ea4 | PARTIALLY_AUTO_FIXED | 1/1 |
| lama_failure | JOB_58241fda790b49d49d865ceb3d875611 | REVIEW_REQUIRED | 0/0 |
| edit_failure | JOB_6dfdc7e4d90c4856819e3b54e3934151 | REVIEW_REQUIRED | 0/0 |
| candidate_byte_drift | JOB_21cc9b1e81fb48c4b0ee759ade722f8c | REVIEW_REQUIRED | 1/1 |

正式CLI任务：D:\GitHub\MyE-C-skill\aliexpress-product-image-audit\work\v2-full-workflow-20261115T170312\retained-cli\bd7e53c93a3e48bc80d50bb9e382e9d7\cli-jobs\JOB_acd9d314ad244efdbab305a11bd5426f，最终PARTIALLY_AUTO_FIXED，1模拟上传/1保存，独立回读通过。该任务明确为Fake，不是Shop7线上PID1的写入。22场景详情v2-full-workflow-fake-evidence.json；CLI证据v2-full-workflow-cli-evidence.json；本地推理v2-full-workflow-local-runtime.json。

Mask外像素与原图SHA未变；完整训练LaMa权重205803670字节，SHA 7ba7aa7ac37a4d41fdbbeba3a2af7ead18058552997e3a3cd1a3b2210c9e6b4c。真实推理使用自有合成图，质量语义检查和保存端仍为Fake，不能推广成真实商品效果。
