"""Validate secret-free, reproducible model gateway profiles without network I/O."""
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit


_FIELDS = ('schema', 'base_url', 'models', 'max_output_tokens', 'retries', 'timeout')
_OPTIONAL_FIELDS = ('reasoning_effort',)
_MODEL_ID = re.compile(r'[A-Za-z0-9_./:-]+', re.ASCII)


def _invalid(field):
    raise ValueError('INVALID_MODEL_CONFIG:' + field) from None


def validate_config(config):
    """Return a fresh normalized profile; never include supplied values in errors."""
    if not isinstance(config, dict):
        _invalid('config')
    if set(config) - set(_FIELDS) - set(_OPTIONAL_FIELDS):
        _invalid('fields')
    for field in _FIELDS:
        if field not in config:
            _invalid(field)
    if config['schema'] != 'model-gateway/v1':
        _invalid('schema')

    base_url = config['base_url']
    if (not isinstance(base_url, str) or not base_url
            or any(character.isspace() or ord(character) < 32 or ord(character) == 127
                   for character in base_url)
            or '?' in base_url or '#' in base_url or '\\' in base_url):
        _invalid('base_url')
    try:
        parsed = urlsplit(base_url)
        hostname = parsed.hostname
        port = parsed.port
        valid = (parsed.scheme in {'http', 'https'} and hostname
                 and parsed.username is None and parsed.password is None
                 and (parsed.scheme == 'https' or hostname in {'127.0.0.1', 'localhost', '::1'}))
        if port is not None and not 1 <= port <= 65535:
            valid = False
    except (ValueError, TypeError):
        _invalid('base_url')
    if not valid:
        _invalid('base_url')

    models = config['models']
    if (not isinstance(models, list) or len(models) not in (1,2)
            or any(not isinstance(model, str) or _MODEL_ID.fullmatch(model) is None
                   for model in models)
            or len({model.casefold() for model in models}) != len(models)):
        _invalid('models')
    for field, low, high in (('max_output_tokens', 1, 16384), ('retries', 0, 2), ('timeout', 1, 150)):
        if type(config[field]) is not int or not low <= config[field] <= high:
            _invalid(field)
    if 'reasoning_effort' in config and (not isinstance(config['reasoning_effort'],str)
            or config['reasoning_effort'] not in ('low','medium','high')):
        _invalid('reasoning_effort')
    normalized = {'schema': config['schema'], 'base_url': base_url.rstrip('/'),
            'models': list(models), 'max_output_tokens': config['max_output_tokens'],
            'retries': config['retries'], 'timeout': config['timeout']}
    if 'reasoning_effort' in config:normalized['reasoning_effort']=config['reasoning_effort']
    return normalized


def load_config(path):
    """Read UTF-8 (including BOM) JSON and apply the same validation contract."""
    try:
        config = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except (OSError, ValueError, TypeError):
        _invalid('file')
    return validate_config(config)


def fingerprint(config):
    """Hash the canonical normalized JSON representation of a valid profile."""
    canonical = json.dumps(validate_config(config), sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


DEFAULT_MODELS = ("deepseek-v4.1-flash",)


def review_models(models):
    """Select the current reviewer even when reading an old pair profile."""
    selected=tuple(m for m in models if m in {'deepseek-v4.1-flash','workbuddy/deepseek-v4.1-flash'})
    if len(selected)!=1:raise ValueError('DEEPSEEK_REVIEW_MODEL_REQUIRED')
    return selected


def require_enabled_model(model):
    """Apply the current user selection at the actual HTTP dispatch boundary."""
    if model not in DEFAULT_MODELS and model not in {"workbuddy/" + m for m in DEFAULT_MODELS}:
        raise ValueError("MODEL_DISABLED_BY_PROJECT_SELECTION")
