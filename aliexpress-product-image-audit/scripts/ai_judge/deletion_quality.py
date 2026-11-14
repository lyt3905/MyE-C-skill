PROMPT='''Independently inspect the FULL original image for a possible deletion, never just a watermark crop.
Return task_type,item_id,decision MATCH/MISMATCH/UNCERTAIN,confidence,abstain,evidence_ids,
is_box (boolean),is_official (boolean),category REDUNDANT/DECORATION/STORE_BANNER/PRODUCT/UNCERTAIN,
information_preserved (boolean).
For the normal single-image mode, MATCH is allowed only for a whole decorative/shop banner with no unique product information, no packaging,
no official studio photograph, no manufacturer branding, copyright, social/photographer signature, disclaimer or useful specification.
A product photograph containing a store watermark is PRODUCT in single-image mode: do not approve deleting the photograph merely to remove its watermark.
REDUNDANT requires a supplied comparison image proving identical product information; without a comparison abstain.
For purpose EXACT_DUPLICATE_WITH_RETAINED_REFERENCE, compare the full source and RETAINED_REFERENCE images.
Only return REDUNDANT/MATCH if the retained image preserves ALL product angles, colors, model, accessories and useful information.
Box/packaging photographs, official studio photos, manufacturer/official marks, copyright, social/photographer signatures remain protected even for duplicate proposals.
Do not approve different angles, accessories, variants or packaging as duplicates. A similarity score is not evidence of redundancy.
Any uncertainty about box, ownership or information loss must abstain. Never give API or deletion instructions.'''
