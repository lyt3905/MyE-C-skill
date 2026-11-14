# 实施映射
|缺陷|实现与验证|
|---|---|
|P0-1|final_state纯函数；service上传前/后校验；7图写前save=0|
|P0-2|compiler/manual_review动作矩阵、target、素材、manifest绑定；KEEP拒删替|
|P0-3|编译uploads，冻结素材、SHA、PIL验证、回填、save/readback；SKU仅按旧URL同步图片字段|
|P0-4|执行前和save前PID/Shop已知字段及current_shop探针核验，hash复读|
|P1-1|AI稳定image_id与商品/SKU规格上下文；未知id拒绝|
|P1-2|自动模板配置、标准CLI required、按店匹配，缺失异常进入review|
|P1-3|manifest含审计/模板/残差/拼图/原图，源文件动态核验；缺manifest旧review拒绝|
|P1-4|JobManager统一恢复与报告更新|
|P1-5|APPLY_MATCHED/STRUCTURE_CHECKED/CONTENT_REVIEWED/VERIFIED分层；报告NOT_VERIFIED|
|P1-6|明确0/未知/未调用/阻断；预算不重试、释放未用预留|
所有本批测试均Mock；真实模型、真实商品只读、上传和写入均未验证。
