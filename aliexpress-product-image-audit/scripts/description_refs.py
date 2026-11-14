"""Compatibility refusals for removed fixed-Description operations.

The field is opaque. These names remain importable only to give old callers a
clear migration error without reading, copying or normalizing their input.
"""
from typing import Any


class DescriptionError(ValueError):
    pass


def parse_description(raw: Any) -> Any:
    raise DescriptionError('DESCRIPTION_OPERATION_FORBIDDEN')


def apply_exact_description_ops(raw: Any, operations: dict[str, Any], resolve_image):
    raise DescriptionError('DESCRIPTION_OPERATION_FORBIDDEN')
