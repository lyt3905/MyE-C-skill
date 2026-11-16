PROMPT='''Independently inspect the FULL original image for a possible deletion, never just a watermark crop.
Return task_type,item_id,decision MATCH/MISMATCH/UNCERTAIN,confidence,abstain,evidence_ids,
is_box (boolean),is_official (boolean),category REDUNDANT/DECORATION/STORE_BANNER/PRODUCT/UNCERTAIN,
information_preserved (boolean).
For the normal single-image mode, MATCH is allowed only for a whole decorative/shop banner with no unique product information, no packaging,
no official studio photograph, no manufacturer branding, copyright, social/photographer signature, disclaimer or useful specification.
A product photograph containing a store watermark is PRODUCT in single-image mode: do not approve deleting the photograph merely to remove its watermark.
For purpose AUTHORIZED_DECORATED_COMPOSITE_REMOVAL, the user instead requires removal of whole shop-made decorative posters/composites.
Independently classify the FULL target composition: a designed border, promotional corner, collaged panels or shop layout around product photographs can be DECORATION even if those panels show boxes.
Set is_decorated_composite=true only for that designed composition, not an ordinary single studio/product/box photograph with a small signature or watermark.
Inspect the supplied RETAINED images. MATCH/DECORATION requires that product identity, useful model evidence and any packaging evidence remain represented there.
Promotional/model captions added to the decorative layout are not unique product evidence when the declared model is supplied separately and retained photographs match the product and packaging.
is_official describes whether the whole target is an official photograph/composition, not whether manufacturer print appears on a photographed box.
Return retained_packaging_verified=true only when retained images visibly preserve the relevant packaging; an authorized decorative composite may have is_box=true without being a protected standalone box photograph.
For a plain box photo or official studio photograph return PRODUCT/MISMATCH and is_decorated_composite=false. Protect copyright and social/photographer credits on ordinary photographs.
The two extra booleans is_decorated_composite and retained_packaging_verified are required in this scoped mode. Do not infer a designed layout merely from printed box graphics.
REDUNDANT requires a supplied comparison image proving identical product information; without a comparison abstain.
For purpose EXACT_DUPLICATE_WITH_RETAINED_REFERENCE, compare the full source and RETAINED_REFERENCE images.
Only return REDUNDANT/MATCH if the retained image preserves ALL product angles, colors, model, accessories and useful information.
Box/packaging photographs, official studio photos, manufacturer/official marks, copyright, social/photographer signatures remain protected even for duplicate proposals.
Do not approve different angles, accessories, variants or packaging as duplicates. A similarity score is not evidence of redundancy.
Any uncertainty about box, ownership or information loss must abstain. Never give API or deletion instructions.'''
