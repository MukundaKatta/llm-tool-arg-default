# llm-tool-arg-default

[![PyPI](https://img.shields.io/pypi/v/llm-tool-arg-default.svg)](https://pypi.org/project/llm-tool-arg-default/)
[![Python](https://img.shields.io/pypi/pyversions/llm-tool-arg-default.svg)](https://pypi.org/project/llm-tool-arg-default/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**Fill missing tool arguments from schema-declared defaults before validation.**

LLMs often skip optional arguments when calling tools. The schema says
`units` defaults to `"celsius"`, but the model sends `{"city": "Tokyo"}`
and drops the field. Downstream validators then either reject the call or
substitute their own defaults silently. This library fills those gaps
explicitly, in one obvious place, before validation runs.

Zero runtime dependencies. Works with JSON-Schema-style dicts and with
Python callables (defaults pulled from the signature).

## Install

```bash
pip install llm-tool-arg-default
```

## Use

### Dict schema

```python
from llm_tool_arg_default import fill_defaults

raw = {"city": "Tokyo"}
schema = {
    "city":  {"type": "string"},
    "units": {"type": "string", "default": "celsius"},
    "lang":  {"type": "string", "default": "en"},
}

result = fill_defaults(raw, schema)

result.args        # {"city": "Tokyo", "units": "celsius", "lang": "en"}
result.filled      # ["units", "lang"]
result.untouched   # ["city"]
```

Existing values win. The raw dict is never mutated.

### Function signature

```python
def weather(city: str, units: str = "celsius", lang: str = "en"):
    ...

result = fill_defaults({"city": "Tokyo"}, weather)
result.args  # {"city": "Tokyo", "units": "celsius", "lang": "en"}
```

Parameters without a default are left missing rather than assigned `None`.

### Nested objects and arrays

```python
schema = {
    "config": {
        "type": "object",
        "properties": {
            "verbose": {"type": "boolean"},
            "retries": {"type": "integer", "default": 3},
        },
    },
    "items": {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "qty":  {"type": "integer", "default": 1},
            },
        },
    },
}

raw = {
    "config": {"verbose": True},
    "items":  [{"name": "a"}, {"name": "b", "qty": 5}],
}

result = fill_defaults(raw, schema)
# config.retries is filled to 3
# items[0].qty is filled to 1; items[1] is untouched
```

### Explicit None as missing

`fill_defaults` only fills truly absent keys. If your model sometimes
emits `{"units": null}` instead of dropping the key, use the safe variant:

```python
from llm_tool_arg_default import fill_defaults_safe

raw = {"city": "Tokyo", "units": None}
fill_defaults_safe(raw, schema, fill_none_with_default=True)
# units gets the default
```

### Default.absent sentinel

To mark a property as "required, no default", set the default to the
sentinel `Default.absent`. The key stays out of the filled args:

```python
from llm_tool_arg_default import Default

schema = {"user_id": {"type": "string", "default": Default.absent}}
```

### Debugging

```python
from llm_tool_arg_default import inspect_schema

inspect_schema(schema)
# {"city": Default.absent, "units": "celsius", "lang": "en"}
```

## Where this fits in the agent stack

This is the **fill** step. Pair it with the rest:

1. [`agent-tool-spec-pack`](https://pypi.org/project/agent-tool-spec-pack/) - generate the schema in the first place.
2. **`llm-tool-arg-default`** (you are here) - fill missing keys from declared defaults.
3. [`llm-tool-arg-coerce`](https://pypi.org/project/llm-tool-arg-coerce/) - coerce string-typed inputs into the right types.
4. [`agentvet`](https://pypi.org/project/agentvet/) - validate the final args before calling the tool.

Running the four in order turns sloppy LLM tool calls into clean,
typed, validated inputs without per-tool boilerplate.

## What it does NOT do

- No type coercion. That is `llm-tool-arg-coerce`'s job.
- No validation. That is `agentvet`'s job.
- No schema generation. That is `agent-tool-spec-pack`'s job.
- No network calls. Pure stdlib (`inspect` only).

## License

MIT
