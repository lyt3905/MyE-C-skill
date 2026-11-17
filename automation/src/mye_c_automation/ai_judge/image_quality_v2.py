from pathlib import Path
SCHEMA_VERSION='image-quality.v2'
PROMPT=(Path(__file__).resolve().parents[1]/'prompts/image_quality.v2.md').read_text(encoding='utf-8')
CHECKS={'identity_preserved','packaging_preserved','protected_print_preserved','overlay_removed','no_new_artifacts'}


def residual_observation(original,checked):
    """Derive an execution input from bound feedback, without rewriting replies."""
    from copy import deepcopy
    from .image_action_decision import validate_watermarks, mark_disposition
    rows=checked.get('judgement',{}).get('results',[])
    if len(rows)!=1 or not rows[0]:return None
    row=rows[0];flags=row.get('checks',{})
    if row.get('decision') not in {'MATCH','MISMATCH'} or row.get('abstain') is not False or not all(flags.get(k) is True for k in CHECKS-{'overlay_removed'}):return None
    marks=row.get('residual_watermarks') if row.get('decision')=='MISMATCH' and flags.get('overlay_removed') is False else None
    if not marks and checked.get('pixel_residual_guard',{}).get('status')=='REMAINS':
        marks=[dict(m,glyph_template_source='ORIGINAL') for m in original['watermarks'] if m.get('action')=='REMOVE_TEXT' and m.get('repair_mode')=='TEMPLATE_GLYPHS' and m.get('glyph_search_scope')=='IMAGE']
    if not marks:return None
    validate_watermarks(marks,allow_unscored=original.get('schema_version')=='image-review.staged-v1')
    result=deepcopy(original)
    result['watermarks']=[m for m in result['watermarks'] if mark_disposition(m)!='REMOVABLE']+deepcopy(marks)
    return result
