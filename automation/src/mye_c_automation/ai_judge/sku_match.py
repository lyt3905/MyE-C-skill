PROMPT = 'Compare SKU specification and image. Return sku_id and image_id exactly as supplied, decision MATCH/MISMATCH/UNCERTAIN. Never invent references.'

PROMPT += " Also return image_type (box/product_only/mixed/unknown), sku_packaging (with_box/without_box/unknown), shared_across_skus and missing_image booleans. Unknown packaging must abstain; do not infer packaging from unrelated text."

PROMPT += (' Required root keys for sku_match: task_type, item_id, sku_id, image_id, decision, confidence, '
           'abstain, evidence_ids, image_type, sku_packaging, shared_across_skus, missing_image. '
           'sku_id and image_id are mandatory even when abstain=true; copy item.sku_id and item.image_id '
           'exactly as supplied. They are request-binding labels, not product database IDs or visual observations. '
           'Never omit those labels, use an SKU name in their place, or guess missing references.')

PROMPT += (' image_type describes the photographed contents: box means retail packaging, including windowed '
           'boxes with the enclosed toy visible and multiple boxed units; product_only means an unpackaged '
           'product with no box; mixed means an unpackaged physical product outside its box alongside separate '
           'packaging. A toy visible through a box window or printed on the box does not make the image mixed.')
