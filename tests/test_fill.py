from llm_tool_arg_default import (
    Default,
    FillResult,
    fill_defaults,
    fill_defaults_safe,
    inspect_schema,
)

# ---------- single-key + multi-key basics ----------


def test_single_missing_key_is_filled():
    raw = {"city": "Tokyo"}
    schema = {
        "city": {"type": "string"},
        "units": {"type": "string", "default": "celsius"},
    }
    result = fill_defaults(raw, schema)
    assert result.args == {"city": "Tokyo", "units": "celsius"}
    assert result.filled == ["units"]


def test_key_present_in_raw_wins_over_default():
    raw = {"city": "Tokyo", "units": "fahrenheit"}
    schema = {
        "city": {"type": "string"},
        "units": {"type": "string", "default": "celsius"},
    }
    result = fill_defaults(raw, schema)
    assert result.args["units"] == "fahrenheit"
    assert "units" not in result.filled


def test_multiple_defaults_filled():
    raw = {"city": "Tokyo"}
    schema = {
        "city": {"type": "string"},
        "units": {"type": "string", "default": "celsius"},
        "lang": {"type": "string", "default": "en"},
    }
    result = fill_defaults(raw, schema)
    assert result.args == {"city": "Tokyo", "units": "celsius", "lang": "en"}
    assert set(result.filled) == {"units", "lang"}


def test_no_defaults_in_schema_returns_raw_unchanged():
    raw = {"a": 1, "b": 2}
    schema = {"a": {"type": "integer"}, "b": {"type": "integer"}}
    result = fill_defaults(raw, schema)
    assert result.args == raw
    assert result.filled == []
    assert set(result.untouched) == {"a", "b"}


def test_returns_fill_result_dataclass():
    result = fill_defaults({}, {"x": {"default": 1}})
    assert isinstance(result, FillResult)


def test_raw_dict_is_not_mutated():
    raw = {"city": "Tokyo"}
    schema = {"units": {"default": "celsius"}}
    fill_defaults(raw, schema)
    assert raw == {"city": "Tokyo"}


# ---------- untouched + filled bookkeeping ----------


def test_untouched_tracks_keys_already_present():
    raw = {"a": 1, "b": 2}
    schema = {"a": {"default": 99}, "c": {"default": "z"}}
    result = fill_defaults(raw, schema)
    assert set(result.untouched) == {"a", "b"}
    assert result.filled == ["c"]


def test_extra_keys_in_raw_pass_through():
    raw = {"city": "Tokyo", "extra_field": "kept"}
    schema = {"units": {"default": "celsius"}}
    result = fill_defaults(raw, schema)
    assert result.args["extra_field"] == "kept"
    assert "extra_field" in result.untouched


# ---------- Default.absent sentinel ----------


def test_default_absent_skips_filling():
    raw: dict = {}
    schema = {"required_field": {"type": "string", "default": Default.absent}}
    result = fill_defaults(raw, schema)
    assert "required_field" not in result.args
    assert result.filled == []


def test_default_absent_does_not_overwrite_present():
    raw = {"required_field": "value"}
    schema = {"required_field": {"type": "string", "default": Default.absent}}
    result = fill_defaults(raw, schema)
    assert result.args == {"required_field": "value"}


def test_default_absent_singleton_identity():
    assert Default.absent is Default.absent  # noqa: PLR0124
    assert repr(Default.absent) == "Default.absent"
    assert bool(Default.absent) is False


# ---------- nested objects ----------


def test_nested_object_recursion_fills_missing_subkey():
    raw = {"config": {"verbose": True}}
    schema = {
        "config": {
            "type": "object",
            "properties": {
                "verbose": {"type": "boolean"},
                "retries": {"type": "integer", "default": 3},
            },
        }
    }
    result = fill_defaults(raw, schema)
    assert result.args["config"] == {"verbose": True, "retries": 3}


def test_nested_object_when_value_missing_at_top_does_nothing_inside():
    raw: dict = {}
    schema = {
        "config": {
            "type": "object",
            "default": {},  # top-level default is an empty dict
            "properties": {
                "retries": {"type": "integer", "default": 3},
            },
        }
    }
    result = fill_defaults(raw, schema)
    # the top-level default was the empty dict the schema declared. nested
    # recursion only happens when the value is present and is a dict.
    assert result.args["config"] == {}


# ---------- arrays of objects ----------


def test_array_of_objects_fills_per_element():
    raw = {"items": [{"name": "a"}, {"name": "b", "qty": 5}]}
    schema = {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "qty": {"type": "integer", "default": 1},
                },
            },
        }
    }
    result = fill_defaults(raw, schema)
    assert result.args["items"] == [
        {"name": "a", "qty": 1},
        {"name": "b", "qty": 5},
    ]


def test_array_with_non_dict_elements_passes_through():
    raw = {"tags": ["x", "y"]}
    schema = {
        "tags": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"qty": {"default": 1}},
            },
        }
    }
    result = fill_defaults(raw, schema)
    assert result.args == {"tags": ["x", "y"]}


# ---------- function signature mode ----------


def test_function_signature_pulls_defaults():
    def weather(city: str, units: str = "celsius", lang: str = "en"):
        return None

    result = fill_defaults({"city": "Tokyo"}, weather)
    assert result.args == {"city": "Tokyo", "units": "celsius", "lang": "en"}
    assert set(result.filled) == {"units", "lang"}


def test_function_signature_no_default_returns_absent():
    def f(city: str, units: str = "celsius"):
        return None

    inspected = inspect_schema(f)
    assert inspected["city"] is Default.absent
    assert inspected["units"] == "celsius"


def test_function_signature_skips_var_args():
    def f(city: str, *args, units: str = "celsius", **kwargs):
        return None

    inspected = inspect_schema(f)
    assert set(inspected.keys()) == {"city", "units"}


def test_function_signature_required_param_not_filled():
    def f(city: str, units: str = "celsius"):
        return None

    result = fill_defaults({}, f)
    # `city` had no default, so it should NOT be in args
    assert "city" not in result.args
    assert result.args == {"units": "celsius"}


# ---------- fill_none_with_default ----------


def test_fill_none_with_default_true_replaces_none():
    raw = {"city": "Tokyo", "units": None}
    schema = {
        "city": {"type": "string"},
        "units": {"type": "string", "default": "celsius"},
    }
    result = fill_defaults_safe(raw, schema, fill_none_with_default=True)
    assert result.args["units"] == "celsius"


def test_fill_none_with_default_false_keeps_explicit_none():
    raw = {"city": "Tokyo", "units": None}
    schema = {
        "city": {"type": "string"},
        "units": {"type": "string", "default": "celsius"},
    }
    result = fill_defaults_safe(raw, schema, fill_none_with_default=False)
    assert result.args["units"] is None


def test_fill_defaults_keeps_explicit_none_by_default():
    raw = {"units": None}
    schema = {"units": {"default": "celsius"}}
    result = fill_defaults(raw, schema)
    # `fill_defaults` itself only fills truly missing keys
    assert result.args["units"] is None


def test_fill_none_keeps_none_when_no_default_declared():
    # explicit None with no declared default must NOT vanish - there is
    # nothing to fill it with, so the key is preserved.
    raw = {"units": None}
    schema = {"units": {"type": "string"}}  # no default
    result = fill_defaults_safe(raw, schema, fill_none_with_default=True)
    assert "units" in result.args
    assert result.args["units"] is None


def test_fill_none_keeps_none_when_default_is_absent_sentinel():
    raw = {"user_id": None}
    schema = {"user_id": {"type": "string", "default": Default.absent}}
    result = fill_defaults_safe(raw, schema, fill_none_with_default=True)
    assert "user_id" in result.args
    assert result.args["user_id"] is None


def test_fill_none_strips_only_keys_with_fillable_default():
    raw = {"a": None, "b": None}
    schema = {
        "a": {"type": "string", "default": "x"},  # fillable
        "b": {"type": "string"},  # no default
    }
    result = fill_defaults_safe(raw, schema, fill_none_with_default=True)
    assert result.args["a"] == "x"
    assert result.args["b"] is None


# ---------- inspect_schema ----------


def test_inspect_schema_returns_defaults_map():
    schema = {
        "a": {"default": 1},
        "b": {"default": "x"},
        "c": {"type": "string"},  # no default declared
    }
    inspected = inspect_schema(schema)
    assert inspected["a"] == 1
    assert inspected["b"] == "x"
    assert inspected["c"] is Default.absent


def test_inspect_schema_handles_json_schema_root():
    schema = {
        "type": "object",
        "properties": {
            "a": {"default": 1},
            "b": {"default": 2},
        },
    }
    inspected = inspect_schema(schema)
    assert inspected == {"a": 1, "b": 2}


# ---------- JSON-Schema root form ----------


def test_json_schema_root_with_properties_is_unwrapped():
    raw = {"city": "Tokyo"}
    schema = {
        "type": "object",
        "properties": {
            "city": {"type": "string"},
            "units": {"type": "string", "default": "celsius"},
        },
    }
    result = fill_defaults(raw, schema)
    assert result.args == {"city": "Tokyo", "units": "celsius"}


# ---------- type / error handling ----------


def test_invalid_schema_type_raises():
    import pytest

    with pytest.raises(TypeError):
        fill_defaults({}, "not a schema")  # type: ignore[arg-type]
