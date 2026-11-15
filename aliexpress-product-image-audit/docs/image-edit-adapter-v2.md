# 本地修复与独立重绘配置的区别

REMOVE_TEXT不需要外部图片编辑API：使用本地OpenCV/LaMa。完整本地权重与配置已准备，见 local/image-options.v2.local.json 及 reports/v2-local-inpaint-runtime.json；现有 --image-options 入口加载并冻结该文件。image_edit仅对应独立AI_REGENERATE，不能当作普通去字前置条件。

# V2 configured image-edit adapter

The existing `workflow_runner.py run --image-options <json>` accepts an optional local image-edit adapter. No provider API or image-generation capability is assumed. The default options omit it and defer AI_REGENERATE.

```json
{
  "rights": "OWNED_OR_LICENSED",
  "max_mask_area": 0.25,
  "image_edit": {
    "adapter_path": "C:/your-installed-adapter/edit_adapter.py",
    "model": "mimo-v2.6-pro"
  }
}
```

Use an already installed Python adapter file implementing `edit_image(source, context, observation, destination)`. Job creation resolves its path and freezes its SHA. An optional `adapter_sha256` must match the file. Adapter loading and invocation happen inside the existing JudgeClient/BudgetManager call; a changed file is rejected. `model` must be one of the two project-selected models and present in the Job's model profile. This is program configuration, never code supplied by a model or an image.

Inputs: source file; sanitized product context without Description; validated unified decision/problem and protected regions; a new output directory. Context also includes `_image_edit_constraints`, the versioned preservation instructions. The adapter must use its configured service and return a dictionary with `candidate_path` plus the actual raw provider `usage` if supplied. A missing usage remains unknown; do not invent values. The candidate must be newly written inside `destination` and must preserve original dimensions, product identity, accessories, actual packaging, factory/product/packaging print and attribution.

The existing prepare path validates candidate bytes and independently checks original/candidate vision quality before uploading. No image generation occurs at configuration loading. No default service credentials, endpoint, additional model, fabricated price or fallback generator is installed here. The separate AI_REGENERATE provider capability remains unverified; local REMOVE_TEXT does not depend on it.

Optional `lama_model_path` points to an existing complete local TorchScript file. A present file's SHA is pinned to the new Job. The adapter supports the installed simple-lama `forward(image, mask)` contract and a TorchScript dictionary contract identified from the model schema. It never downloads weights. Synthetic TorchScript tests prove data contract/padding/output shape only, not trained LaMa quality.
