"""llm-tool-arg-default - fill missing tool args from schema defaults.

LLMs often skip optional arguments when calling tools. They pass
``{"city": "Tokyo"}`` and drop ``units`` even though the schema says
``units`` defaults to ``"celsius"``. This library fills those gaps from
the schema before validation or coercion fires downstream.

    from llm_tool_arg_default import fill_defaults

    raw = {"city": "Tokyo"}
    schema = {
        "city": {"type": "string"},
        "units": {"type": "string", "default": "celsius"},
        "lang": {"type": "string", "default": "en"},
    }
    result = fill_defaults(raw, schema)
    # result.args == {"city": "Tokyo", "units": "celsius", "lang": "en"}
    # result.filled == ["units", "lang"]

Schemas can also be plain callables, in which case defaults are pulled
from the function signature:

    def weather(city: str, units: str = "celsius", lang: str = "en"):
        ...

    result = fill_defaults({"city": "Tokyo"}, weather)

Sibling libraries in the same agent stack:

  * ``agent-tool-spec-pack`` - generate the schema in the first place
  * ``llm-tool-arg-coerce`` - coerce types after the defaults are filled
  * ``agentvet`` - validate the final args before invoking the tool
"""

from llm_tool_arg_default.fill import (
    Default,
    FillResult,
    fill_defaults,
    fill_defaults_safe,
    inspect_schema,
)

__version__ = "0.1.0"

__all__ = [
    "Default",
    "FillResult",
    "__version__",
    "fill_defaults",
    "fill_defaults_safe",
    "inspect_schema",
]
