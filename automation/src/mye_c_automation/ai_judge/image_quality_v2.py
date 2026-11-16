from pathlib import Path
SCHEMA_VERSION='image-quality.v2'
PROMPT=(Path(__file__).resolve().parents[1]/'prompts/image_quality.v2.md').read_text(encoding='utf-8')
CHECKS={'identity_preserved','packaging_preserved','protected_print_preserved','overlay_removed','no_new_artifacts'}
