PROMPT = '''Compare candidate original image (first), source original (SOURCE), and candidate highpass/residual (RESIDUAL).
Return decision MATCH only if same model, color, packaging and product content is preserved AND candidate is clean.
Return a nested JSON object under the key "checks", never top-level check fields.
The checks object must contain all these boolean fields: product_identity_match, source_clean, candidate_visual_validation,
protected_elements_preserved, residual_pass, subject_bounds_safe, model_match, packaging_match, official_source.
Residual is evidence for localization; never infer cleanliness from a residual pixel count alone.
Official/social/photographer signatures, factory print and disclaimers must remain. Unknown ownership must abstain.
Also return image_type BOX/FIGURE/MIXED/UNCERTAIN, model (only observed), color (only observed).
Cropping must preserve product/box and complete official text; erasure must not damage texture.
No API instructions. All claims must reference evidence_ids provided. Missing checks are failures.'''
