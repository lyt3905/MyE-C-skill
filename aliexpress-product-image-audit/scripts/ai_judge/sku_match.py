PROMPT = 'Compare SKU specification and image. Return sku_id and image_id exactly as supplied, decision MATCH/MISMATCH/UNCERTAIN. Never invent references.'

PROMPT += " Also return image_type (box/product_only/mixed/unknown), sku_packaging (with_box/without_box/unknown), shared_across_skus and missing_image booleans. Unknown packaging must abstain; do not infer packaging from unrelated text."
