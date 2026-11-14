# 真实只读联调记录（进行中）

- 范围：用户指定既有本地站点配置，Shop 7待审核列表；不上传、不保存、不翻译、不发布。
- 模型网关鉴权成功，模型列表含glm-5v-turbo与kimi-k3-1。
- 两模型真实合成图片识字探针均正确；GLM约2.52秒、Kimi约4.34秒，均返回usage。仅证明连通性。
- 当前会话已核验Shop 7；PENDING共367件，首批5017/5019/5099。READY_TO_PUBLISH为0，当前CLI pending状态与真实待处理队列不一致，需后续修复。
- 商品5017真实audit_one执行：main6/detail6/sku2，下载错误0，OCR启用，OCR命中9，边框候选7、残差候选2。原始证据位于work/integration-20261112/shop7-5017。
- 详情无shopId字段；不可伪造该绑定验证通过，线上自动写入继续关闭。
- 实际JudgeClient调用出现JSONDecodeError，捕获原始响应确认完整Markdown JSON围栏；正修复严格包装兼容，不放宽业务Schema。
- 无生产商品变更。密钥不写入文件或报告。


## JSON兼容修复与真实复测

子智能体按用户偏好使用GPT-6.1 Sol轻度推理，仅修改客户端和新增解析测试。严格接受纯JSON或完整单一JSON代码围栏；混杂/残缺/多个围栏与非法业务Schema继续拒绝。相关10项测试通过。

商品5017首张主图经修复后的标准JudgeClient真实调用两个模型：GLM marketing_text(.95)，Kimi third_party_store_logo(.93)。结果REVIEW，分类分歧正确不授权整改；真实调用2次，usage可用，total_tokens=2948。只证明本张图响应与保守分歧处理有效，不能外推全商品审核质量。原始记录real_model_probe_after_fix.json保存在工作证据目录，未保存密钥。

完整回归正在运行；Shop7待处理状态过滤与缺失shopId字段仍需后续联调修复，自动写入关闭。


## Shop7完整只读Workflow

Job：JOB_6a0eea890d4c413eb9df37c7c46447f6。audit模式，授权enabled=false，模型上限12。执行结束DEFERRED，14个延后项，无商品写入。真实请求12次，usage返回15667 Token；模板REQUIRED_TEMPLATE_MISSING。判断含ValueError7项、预算阻断2项；不能声称全部模型审核通过。

店铺绑定复核：商品5017没有shopId/shop_id/shop键，PID正确且属于Shop7查询列表；读取前后current_shop均7，原ExecutorService._identity直接通过，无需更改或绕过。

待处理选择已修复PENDING/page=1，读取前后Shop检查、非PENDING响应拒绝；4项测试通过，新函数真实读取返回5017/5019/5099。

追加真实诊断表明GLM响应缺owner/location，报identity/fields；正在修正任务提示的一致性，继续保留严格Schema，不猜测补值。JSON解析修复完整回归303次/49.616秒/OK；本轮新增筛选修复仍需最终回归。

提示词修复真实复测WM_MAIN_001：双模型均third_party_store_banner，GLM .95、Kimi .82，低置信度正确REVIEW；请求2次/3065 Token。发现既有Shop7模板choice-toy-confirmed.npy与旧只读Job3289配置，但其覆盖本次商品水印的适用性尚未核实，不能仅凭文件名解除模板缺失。


## 模板离线泛化试验

旧CHOICE TOY模板不适用于本商品店铺文字。新模板离线实验（子智能体6.1 Sol低推理）在7个唯一源图上：独立正例NCC .924，但另两正例仅.434/.368出现漏检，负例包装图.446/.428；平坦窗口排除仍有效。判定不可靠，不配置。完整来源ROI/SHA和复现见work/integration-20261112/template-trial/REPORT.md。模型与模板分工不变，不以模板低分认定干净，不擦商品本体。

标题试生成暴露英文子串品牌误匹配及身份丢失，独立validate_title结果ok=false，但其底层为Schema ValueError，不能称语义成功拒绝。标题规则正补失败测试与最小修复。所有生产写入仍关闭。

英文标题规则已修复完整词匹配与身份冲突：birthday不误匹配RT，真实5017源角色冲突直接DEFERRED/SOURCE_ROLE_CONFLICT；10标题测试通过。公共响应契约新增数值confidence/布尔abstain/精确ID和证据约束，原Schema保持严格；契约文本进入缓存哈希，14相关测试通过，真实复测及完整回归待收取。
