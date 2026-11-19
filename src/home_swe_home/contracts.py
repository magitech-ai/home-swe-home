"""Strict local request contracts for the Gemini Interactions API.

These models mirror the documented request shape. They exist because the
installed SDK's generated models use ``extra="allow"`` and happily accept
invented nested shapes — including a ``function_result.result`` wrapped in a
``content`` object instead of being an array. Building requests through these
models makes the wire shape fail closed.

Primary sources:
- <https://ai.google.dev/gemini-api/docs/interactions> (request fields,
  thinking_level / thinking_summaries domains, function-result shape)
- <https://ai.google.dev/gemini-api/docs/openai> (OpenAI-compatibility mapping)

The SDK's private ``_gaos`` models are deliberately not imported: they are
generated internals and may change without notice.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

DOC_INTERACTIONS = "https://ai.google.dev/gemini-api/docs/interactions"
DOC_OPENAI_COMPAT = "https://ai.google.dev/gemini-api/docs/openai"

THINKING_LEVELS = ("minimal", "low", "medium", "high")
THINKING_SUMMARIES = ("auto", "none")


class StrictModel(BaseModel):
    """Base that rejects unknown fields and cannot be mutated after build."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class TextContent(StrictModel):
    """A documented text content part."""

    type: Literal["text"]
    text: str


class FunctionResult(StrictModel):
    """A documented function_result step.

    ``result`` is an array of content parts, not ``{"content": [...]}``. The
    latter was an invented shape that the SDK accepted silently.
    """

    type: Literal["function_result"]
    name: str
    call_id: str
    result: list[TextContent]


class FunctionTool(StrictModel):
    """The documented function tool declaration."""

    type: Literal["function"]
    name: str
    description: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)


class NativeGenerationConfig(StrictModel):
    """The subset of generation_config fields this adapter sends."""

    thinking_level: str | None = None
    thinking_summaries: Literal["auto", "none"] | None = None

    @field_validator("thinking_level")
    @classmethod
    def _known_level(cls, value: str | None) -> str | None:
        if value is not None and value not in THINKING_LEVELS:
            raise ValueError(f"unknown thinking_level {value!r}")
        return value


class NativeRequest(StrictModel):
    """A CreateModelInteraction request, restricted to fields we actually use."""

    model: str
    input: list[TextContent] | list[FunctionResult]
    system_instruction: str | None = None
    tools: list[FunctionTool] | None = None
    stream: bool = True
    store: bool = True
    previous_interaction_id: str | None = None
    generation_config: NativeGenerationConfig | None = None

    def wire(self) -> dict[str, Any]:
        """Return the exact JSON body, omitting fields we did not set."""
        return self.model_dump(exclude_none=True)
