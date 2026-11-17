# Codex 执行目标：开发通用 Watermark Processing Module

## 一、执行任务

请根据以下开发任务书，在现有独立软件 `automation/`
中完成通用水印处理模块的审计、设计、实现、测试和集成：

`automation/docs/通用水印处理模块_开发任务书_V1.0.md`

本次开发基线：

`68e168f1a08c6338cb0964dffbd021bb5e484556`

目标是建设一个与商品业务解耦、由 AI Vision
决策驱动的通用水印处理模块。不要将它开发成 GCC 专用去水印程序。

## 二、执行前检查

首先检查：

``` bash
git status --short --branch
git rev-parse HEAD
git branch --show-current
git diff
git diff --cached
```

确认当前分支、HEAD、工作区修改、`automation/`
实际状态、现有水印处理能力，以及 LaMa 安装和模型权重位置。

不得假设当前工作区和历史任务书完全一致。发现已有实现时，先判断是否可复用，不得重复创建。

不得使用 Git Reset、Clean、强制 Checkout 或其他可能覆盖工作区的命令。

## 三、必须先审计的现有模块

重点检查：

1.  DeepSeek Vision 客户端。
2.  视觉审核 Prompt。
3.  图片审核 JSON Schema。
4.  `REMOVE_TEXT` 决策流程。
5.  `watermark_mask_builder` 相关实现。
6.  `watermark_remover` 相关实现。
7.  OpenCV 修复能力。
8.  LaMa 安装、权重和调用接口。
9.  AI 图片质量复核。
10. 图片 SHA256 和文件缓存。
11. 现有工作流和 Plan 编译器。

优先复用现有模块。如果已有某项能力，只补充缺失部分。

## 四、架构实施要求

必须遵守：

``` text
现有 DeepSeek Vision
    ↓
现有图片动作决策
    ↓
REMOVE_TEXT
    ↓
Watermark Processing Module
    ↓
Mask 生成
    ↓
OpenCV / LaMa
    ↓
确定性质量检查
    ↓
现有 DeepSeek Vision 质量复核
    ↓
PASS / REVIEW / FAIL
    ↓
返回现有商品整改流程
```

模块不直接创建或管理新的 DeepSeek
客户端，不在模块内部重新判断水印语义，不新建第二套 AI 视觉审核系统。

## 五、通用性要求

不得写死 GCC、店铺名称、水印文字、固定品牌、字体、颜色、角度或排列方式。

必须处理 AI 返回的多个水印 polygon，支持： - 单个水印。 -
重复斜向水印。 - 横向重复水印。 - 纵向重复水印。 - 网格水印。 -
不规则排列。 - 半透明水印。 - 图形与文字组合。 - 多组水印。

程序只使用 AI 提供的语义识别结果和确定性几何处理。

禁止新增 OCR、独立文字检测模型、模板匹配水印识别和传统 CV 语义分类器。

## 六、LaMa 实施要求

优先使用当前已经安装的 LaMa。

必须确认： - 模型权重存在。 - 权重路径可配置。 - 模型可以加载。 -
输入图片和 Mask 正常。 - 可以完成真实本地推理。 -
输出图片能够正常解码。 - 原图不会被覆盖。

LaMa
不能正常运行时，先分析依赖、权重和设备问题。不得静默回退为原图并标记成功。

不安装 MAT 和 Stable Diffusion Inpainting。

## 七、算法路由

实现统一修复接口：

-   小面积、简单背景：优先 OpenCV Telea。
-   Telea 备用：OpenCV Navier-Stokes。
-   大面积、复杂纹理和半透明水印：使用 LaMa。

算法选择参数必须可配置，并记录实际选择理由。不允许所有图片无差别调用
LaMa。

## 八、必须重点解决的问题

### 8.1 多水印处理

一个图片可能存在多个水印。必须做到：

-   每个实例独立记录。
-   支持分组。
-   支持局部 ROI。
-   支持相邻区域合并。
-   避免不相邻区域形成巨大 Mask。
-   支持分批修复。
-   保留完整上下文。
-   每个区域可追溯。

### 8.2 商品保护

必须保护商品本体、型号、原厂
Logo、商品自身印刷、包装印刷、重要机械结构和配件。出现保护区域冲突时转
`REVIEW`。

### 8.3 原图保护

-   不覆盖原图。
-   不删除原始证据。
-   输出使用新文件。
-   记录输入和输出 SHA256。
-   检查 Mask 外非预期变化。

### 8.4 失败处理

最多允许一次预设备用算法重试。不能无限修复。商品结构变化、授权不明确、坐标无效等情况必须安全停止。

## 九、开发执行顺序

按照以下顺序实施，不要跳过前置阶段。

### Phase 1：审计

输出： - `automation/reports/watermark-module-audit.md` -
`automation/reports/lama-environment-check.md`

### Phase 2：接口设计

输出通用输入契约、通用输出契约、Schema 版本和接口测试。

### Phase 3：Mask 和区域管理

实现 Input Parser、Region Manager、Mask Builder。

### Phase 4：本地修复

实现 Repair Router、OpenCV Adapter、LaMa Adapter、Inpainting Engine。

### Phase 5：质量检查

实现文件检查、SHA 检查、Mask 外区域检查、失败处理和 AI 复核接口。

### Phase 6：工作流整合

接入现有 `REMOVE_TEXT`。不创建新的总 Runner，不改变现有
KEEP、DELETE、AI_REGENERATE 和 REVIEW 的业务含义。

### Phase 7：测试与验收

运行完整的独立测试和集成测试。

## 十、测试要求

至少建立以下测试：

1.  单个水印。
2.  多个重复水印。
3.  多个斜向水印。
4.  不同倾斜角度。
5.  不同文字内容。
6.  不同透明度。
7.  不规则排列。
8.  多组水印。
9.  黑色背景。
10. 白色背景。
11. 复杂商品表面。
12. 商品自身文字保护。
13. 原厂 Logo 保护。
14. 包装印刷保护。
15. Mask 坐标错误。
16. Mask 面积超限。
17. LaMa 加载失败。
18. LaMa 推理失败。
19. 水印修复不完整。
20. 修复破坏商品结构。
21. 原图保护。
22. Mask 外区域保护。

必须分别报告单元测试、Fake 集成测试、DeepSeek Mock 测试、真实 DeepSeek
测试和真实 LaMa 本地推理测试。

真实 DeepSeek API 调用和线上商品操作默认关闭。没有单独授权时，不得执行。

## 十一、开发保护要求

1.  所有新实现和修改只允许发生在 `automation/`。
2.  原 `aliexpress-product-image-audit/` 完整保留。
3.  不复制整个 Skill 目录。
4.  不在 automation 中运行时读取原 Skill 文件。
5.  不修改原有 V2 业务规则。
6.  不改变 Description 的既定处理边界。
7.  不增加 OCR。
8.  不增加其他视觉模型。
9.  不安装 MAT。
10. 不安装 Stable Diffusion。
11. 不调用线上商品写入接口。
12. 不擅自 Git Commit。
13. 不擅自 Git Push。
14. 不删除现有测试或历史数据。

模型置信度和 Token 使用量沿用当前基线的 `RECORD_ONLY`
策略，不擅自增加新的数值放行门槛。

## 十二、最终交付

目录结构以现有项目实际情况为准，不得为了匹配示例而重复创建模块。目标交付包括：

-   水印处理模块源码。
-   对应测试。
-   `automation/reports/watermark-module-audit.md`
-   `automation/reports/lama-environment-check.md`
-   `automation/reports/watermark-module-contract.md`
-   `automation/reports/generic-watermark-processing-module.md`
-   `automation/reports/watermark-module-test-report.md`

最终报告必须说明：

1.  新增了哪些模块。
2.  复用了哪些已有模块。
3.  修改了哪些文件。
4.  LaMa 是否真实运行成功。
5.  DeepSeek Vision 接口是否完成验证。
6.  多水印处理是否通过测试。
7.  Mask 是否符合预期。
8.  商品保护测试是否通过。
9.  失败回退是否有效。
10. 是否完成现有 REMOVE_TEXT 集成。
11. 是否存在未完成项目。
12. 当前是否可以进入下一阶段。

所有结果必须标记： - `IMPLEMENTED` - `FAKE_VERIFIED` -
`REAL_MODEL_VERIFIED` - `BLOCKED` - `NOT_RUN`

不得夸大测试结果。

## 十三、Codex 启动消息

请先阅读：

1.  `automation/docs/通用水印处理模块_开发任务书_V1.0.md`
2.  `automation/docs/Codex执行目标_通用水印处理模块.md`

以仓库当前实际代码为准，以 Commit `68e168f` 的 V2 业务规则为基线。

本次任务是开发通用 Watermark Processing Module，不是开发 GCC
专用去水印程序。

请先审计 automation 中已有的 DeepSeek Vision、Mask、OpenCV、LaMa 和
REMOVE_TEXT 实现，确认现有能力后再制定具体修改计划。

重点检查模块独立性、重复水印通用性、多区域 Mask、LaMa
实际推理、商品结构保护和失败回退。

审计完成后直接按照任务书 Phase 1 至 Phase 7 执行。

所有实现只允许修改 automation/，原 Skill 项目必须完整保留。

不要增加 OCR、MAT、Stable Diffusion，不要重复创建 AI
客户端或总工作流，不要进行线上商品写入，不要擅自 Commit 或 Push。

完成后提供完整测试报告、修复前后对比图、Mask 可视化结果和未完成事项。

## 十四、执行方式

先审计，再实施。按照 Phase 1 至 Phase 7
连续推进所有安全且已经授权的任务，不要在每完成一个小步骤后等待确认。

如果发现现有代码与任务书存在冲突：

-   先检查 68e168f 的正式规则。
-   检查当前 automation 实际实现。
-   优先复用成熟实现。
-   保留用户已有修改。
-   在报告中解释冲突和处理方式。

遇到无法安全解决的问题时，停止对应部分并明确报告，不得自行降低保护要求。

最终目标：

交付一个真正可独立调用、通用、不依赖特定店铺或水印内容的 Watermark
Processing Module，并将其稳定接入现有 MyE-C V2 图片审核与整改流程。
