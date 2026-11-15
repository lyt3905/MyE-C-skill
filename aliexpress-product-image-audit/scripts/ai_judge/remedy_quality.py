PROMPT = '''Compare candidate original image (first), source original (SOURCE), and candidate highpass/residual (RESIDUAL).
Return decision MATCH only if same model, color, packaging and product content is preserved AND candidate is clean.
When item.purpose specifies type CONFIRMED_MARK_REPAIR, this is a scoped repair already authorized by the dual-model watermark audit.
In that scope, source_clean means the confirmed seller mark has been removed from the candidate; unrelated unresolved text/marks remain tracked separately.
protected_elements_preserved means product/box/factory print/photographer credits are preserved, excluding the explicitly authorized seller overlay.
Verify identity preservation from unchanged product pixels; the model code need not be newly readable to establish that a border crop preserved the same object.
Confidence describes verification of this scoped change, not certainty about all unrelated image text. Do not claim global compliance.
For phase POST_WRITE_READBACK, SOURCE is the approved candidate image; verify the first image preserves that approved content and scoped repair.
For other purposes, apply the ordinary whole-candidate cleanliness checks.
Return a nested JSON object under the key "checks", never top-level check fields.
The checks object must contain all these boolean fields: product_identity_match, source_clean, candidate_visual_validation,
protected_elements_preserved, residual_pass, subject_bounds_safe, model_match, packaging_match, official_source.
Residual is evidence for localization; never infer cleanliness from a residual pixel count alone.
Official/social/photographer signatures, factory print and disclaimers must remain. Unknown ownership must abstain.
Also return image_type BOX/FIGURE/MIXED/UNCERTAIN, model (only observed), color (only observed).
Cropping must preserve product/box and complete official text; erasure must not damage texture.
No API instructions. All claims must reference evidence_ids provided. Missing checks are failures.'''
