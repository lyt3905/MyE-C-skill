"""Installed package-owned, read-only business resources."""
from pathlib import Path

def resource_path(name):
    root=Path(__file__).resolve().parent
    path=(root/name).resolve()
    if not path.is_relative_to(root):raise ValueError('RESOURCE_OUTSIDE_PACKAGE')
    if not path.exists():raise FileNotFoundError(name)
    return path

def validate_resource_json(value,schema_name):
    """Validate local configuration without remote schema resolution."""
    import json
    from jsonschema import Draft202012Validator,ValidationError
    schema=json.loads(resource_path('config/schemas/'+schema_name).read_text(encoding='utf-8'))
    try:Draft202012Validator(schema).validate(value)
    except ValidationError as exc:raise ValueError('CONFIG_SCHEMA_INVALID:'+schema_name) from exc
    return value
