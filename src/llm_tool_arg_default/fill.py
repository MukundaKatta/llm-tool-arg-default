"""Fill missing tool args from schema-declared defaults."""

from __future__ import annotations

import copy
import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


class _Absent:
    """Sentinel class for `Default.absent` - means "no default; leave key missing"."""

    _instance: _Absent | None = None

    def __new__(cls) -> _Absent:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "Default.absent"

    def __bool__(self) -> bool:
        return False


class Default:
    """Namespace for default-related sentinels.

    `Default.absent` marks a schema property as having no default; the key
    is left out of the filled args rather than being assigned `None` or any
    other placeholder.
    """

    absent: _Absent = _Absent()


@dataclass
class FillResult:
    """Result of `fill_defaults`.

    Attributes:
      args: the filled argument dict (a new dict, raw is not mutated)
      filled: list of keys (top-level) that were added by this call
      untouched: list of keys (top-level) that were already present in raw
    """

    args: dict[str, Any]
    filled: list[str] = field(default_factory=list)
    untouched: list[str] = field(default_factory=list)


def _signature_defaults(fn: Callable[..., Any]) -> dict[str, Any]:
    """Pull defaults out of a function signature as a JSON-Schema-style dict.

    Parameters without a default (or with `inspect.Parameter.empty`) become
    `Default.absent` so the rest of the fill pipeline can skip them.
    """
    sig = inspect.signature(fn)
    out: dict[str, Any] = {}
    for name, param in sig.parameters.items():
        if param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        default = param.default
        if default is inspect.Parameter.empty:
            out[name] = {"default": Default.absent}
        else:
            out[name] = {"default": default}
    return out


def _normalize_schema(schema: dict[str, Any] | Callable[..., Any]) -> dict[str, Any]:
    """Normalize a schema input into a property map keyed by name.

    Accepts:
      * a JSON-Schema-style root: ``{"type": "object", "properties": {...}}``
      * a flat property map: ``{"key": {"type": ..., "default": ...}}``
      * a callable - defaults pulled from its signature
    """
    if callable(schema):
        return _signature_defaults(schema)
    if not isinstance(schema, dict):
        raise TypeError(f"schema must be a dict or callable, got {type(schema).__name__}")
    # JSON-Schema root with "properties"
    if "properties" in schema and isinstance(schema["properties"], dict):
        return schema["properties"]
    return schema


def _fill_value(value: Any, prop_schema: Any) -> Any:
    """Recurse into objects and arrays of objects to fill nested defaults.

    Returns the (possibly transformed) value. Non-dict, non-list values pass
    through unchanged.
    """
    if not isinstance(prop_schema, dict):
        return value

    schema_type = prop_schema.get("type")

    if schema_type == "object" and isinstance(value, dict):
        nested_props = prop_schema.get("properties")
        if isinstance(nested_props, dict):
            nested_result = fill_defaults(value, nested_props)
            return nested_result.args

    if schema_type == "array" and isinstance(value, list):
        items_schema = prop_schema.get("items")
        if (
            isinstance(items_schema, dict)
            and items_schema.get("type") == "object"
            and isinstance(items_schema.get("properties"), dict)
        ):
            return [
                fill_defaults(elem, items_schema["properties"]).args
                if isinstance(elem, dict)
                else elem
                for elem in value
            ]

    return value


def fill_defaults(
    raw: dict[str, Any],
    schema: dict[str, Any] | Callable[..., Any],
) -> FillResult:
    """Fill missing keys in `raw` from schema-declared defaults.

    Existing values in `raw` always win - this only adds keys that are
    absent. Nested objects and arrays of objects recurse so deeply-nested
    defaults get filled too.

    Args:
      raw: caller-supplied arg dict (often a tool call from an LLM).
      schema: either a property map (key -> {"type": ..., "default": ...}),
        a JSON-Schema root with "properties", or a callable whose signature
        carries the defaults.

    Returns:
      A `FillResult` with the merged args plus bookkeeping of what changed.
    """
    properties = _normalize_schema(schema)

    out: dict[str, Any] = dict(raw)
    filled: list[str] = []
    untouched: list[str] = list(raw.keys())

    for key, prop_schema in properties.items():
        present = key in raw
        default = (
            prop_schema.get("default", Default.absent)
            if isinstance(prop_schema, dict)
            else Default.absent
        )

        if not present:
            if default is Default.absent:
                # explicit "no default" sentinel - leave key missing
                continue
            # deep-copy so a mutable default (e.g. [] or {}) declared in the
            # schema is never aliased into the result; otherwise mutating one
            # call's filled value would corrupt the default for every later
            # call (the classic mutable-default footgun).
            out[key] = copy.deepcopy(default)
            filled.append(key)
        else:
            # value present - recurse into nested defaults if applicable
            out[key] = _fill_value(out[key], prop_schema)

    return FillResult(args=out, filled=filled, untouched=untouched)


def fill_defaults_safe(
    raw: dict[str, Any],
    schema: dict[str, Any] | Callable[..., Any],
    *,
    fill_none_with_default: bool = True,
) -> FillResult:
    """Like `fill_defaults`, with an extra knob for explicit None values.

    LLMs sometimes emit ``{"units": null}`` instead of dropping the key.
    When ``fill_none_with_default=True`` (the default for this variant),
    those explicit None entries are treated the same as missing and get
    replaced by the schema default if one exists.

    An explicit None is only stripped when the schema declares a usable
    (non-``Default.absent``) default for that key; otherwise there is
    nothing to fill it with, so the None is preserved rather than silently
    dropped.

    When ``fill_none_with_default=False`` the behavior matches
    `fill_defaults` exactly.
    """
    if not fill_none_with_default:
        return fill_defaults(raw, schema)

    properties = _normalize_schema(schema)

    def _has_fillable_default(key: str) -> bool:
        prop_schema = properties.get(key)
        if not isinstance(prop_schema, dict):
            return False
        return prop_schema.get("default", Default.absent) is not Default.absent

    # treat explicit-None as missing, but only strip keys we can actually
    # refill from a declared default - otherwise keep the None as-is
    stripped = {k: v for k, v in raw.items() if v is not None or not _has_fillable_default(k)}
    return fill_defaults(stripped, schema)


def inspect_schema(schema: dict[str, Any] | Callable[..., Any]) -> dict[str, Any]:
    """Return the defaults map for a schema, for debugging.

    Each schema key maps to its declared default, or `Default.absent` if it
    has none. Useful for catching tool definitions that forgot a default
    where the LLM never sends the field.
    """
    properties = _normalize_schema(schema)
    out: dict[str, Any] = {}
    for key, prop_schema in properties.items():
        if isinstance(prop_schema, dict):
            out[key] = prop_schema.get("default", Default.absent)
        else:
            out[key] = Default.absent
    return out
