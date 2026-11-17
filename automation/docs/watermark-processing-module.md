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

不包含版权自动推断、文字识别、店铺专用判断或线上写入。AI漏报的区域不会被程序自动认成新水印；需要原审核或人工提供完整区域。复杂结构和印刷重叠无法安全处理时REVIEW，不能以删除整张商品图兜底。
