# 通用水印模块 Python API

模块：mye_c_automation.watermark_processing；具体契约见 ../reports/watermark-module-contract.md。

```python
import json
from pathlib import Path
from mye_c_automation.watermark_processing import process_watermarks
from mye_c_automation.image_repairs_v2 import lama_torchscript

request = json.loads(Path("input.json").read_text(encoding="utf-8"))
# request里的授权来自程序配置；水印/保护坐标来自现有AI观测。
# 权重必须已存在且SHA匹配；不联网下载。可按worker复用已加载适配器。
lama = lama_torchscript("models/lama/big-lama.pt", "已校验的权重SHA256")
result = process_watermarks(request, "new-output-directory", lama=lama,
                            policy={"context_pixels": 24, "max_roi_area": 0.45})
if result["processing_status"] == "PROCESSED":
    # 送既有VisualQualityInspector.inspect_v2复核；禁止在这里直接上传。
    print(result["output_path"], result["mask_paths"], result["quality_status"])
else:
    print(result["failure_reason"])
```

只处理简单小区域时，可不传lama；若实际路由需要LaMa，缺少后端会返回FAILED，绝不返回原图冒充成功。正式V2入口已经按需加载本地模型；使用原myec-automation流程即可，不必另跑第三个总工作流。直接API不创建Job和预算。

可单独调用六个组件：WatermarkInputParser.parse、WatermarkMaskBuilder.build、WatermarkRegionManager.plan、RepairRouter.select、InpaintingEngine.run、WatermarkQualityChecker.check。稳定业务集成入口优先使用process_watermarks或原remove_text，避免绕过统一检查。

可配置参数保存在现有local/image-options.local.json的watermark_processing对象，示例：

```json
{"watermark_processing":{"context_pixels":16,"adjacency_pixels":8,"dilation":2,"max_roi_area":0.45,"opencv_max_mask_area":0.04,"opencv_max_roi_area":0.20,"radius":3}}
```

不包含版权自动推断、文字识别、店铺专用判断或线上写入。AI漏报的区域不会被程序自动认成新水印；需要原审核或人工提供完整区域。风险观察不单独阻止试修；固定保护冲突、无效输入或实际修复后质量问题分别报告，不能以删除整张商品图兜底。

0.2.33 已加入单处、多处及大面积半透明文字的自动选样本/字形掩膜，以及带上下文的重叠分块和融合。默认无需人工提供模板框；无可靠样本时保留明确的原始区域回退。完整配置、边界与验收见 [通用文字水印处理](general-text-watermarks.md)。

0.2.35 在既有remove_text入口默认优先进行重复图案精细字形匹配，并按已批准政策处理少量印刷重叠。直接process_watermarks低层API仍按调用者明确输入执行；默认产品主流程的派生规划、原回复分离及策略开关见 [默认精细字形去水印](default-precise-watermarks.md)。

0.2.37：产品remove_text默认protection_overlap_trial=true，保护重叠及旧印刷比例延后到实际候选审核；低层process_watermarks仍默认严格，可显式传入对应policy开启。原始保护标注、源/候选/Mask绑定的变化数据和实际质量通过证明均保留。见 [本地试修与实际保护复核](overlap-trial-review.md)。


2026-11-18 / 0.2.38：正常商品V2去水印失败后的第二轮默认使用OCR备选，说明见[ocr-watermark-fallback.md](ocr-watermark-fallback.md)。通用process_watermarks自身不调用语义模型；由现有商品prepare负责调度OCR备选及质量审核。
