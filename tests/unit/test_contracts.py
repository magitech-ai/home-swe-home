"""Tests for the strict, doc-sourced Gemini request contracts.

Golden fixtures here are transcribed from Gemini's primary documentation, not
from this adapter's output. Generating them from our own behaviour would
enshrine any invented shape (D-009).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from home_swe_home.contracts import (
    DOC_INTERACTIONS,
    FunctionResult,
    NativeGenerationConfig,
    NativeRequest,
    TextContent,
)


def test_contract_points_at_primary_docs() -> None:
    assert DOC_INTERACTIONS.startswith("https://ai.google.dev/gemini-api/docs/")


def test_rejects_invented_function_result_shape() -> None:
    # The SDK accepts this; our contract must not. The documented `result` is
    # an array of content parts, not an object with a `content` key.
    with pytest.raises(ValidationError):
        FunctionResult.model_validate(
            {
                "type": "function_result",
                "name": "run_command",
                "call_id": "fc_1",
                "result": {"content": [{"type": "text", "text": "OK"}]},
            }
        )


def test_accepts_documented_function_result_shape() -> None:
    result = FunctionResult.model_validate(
        {
            "type": "function_result",
            "name": "run_command",
            "call_id": "fc_1",
            "result": [{"type": "text", "text": "OK"}],
        }
    )
    assert result.result == [TextContent(type="text", text="OK")]


def test_rejects_unknown_top_level_field() -> None:
    with pytest.raises(ValidationError):
        NativeRequest.model_validate(
            {
                "model": "gemini-4-neon",
                "input": [{"type": "text", "text": "hi"}],
                "invented_field": True,
            }
        )


def test_rejects_unknown_thinking_level() -> None:
    with pytest.raises(ValidationError, match="unknown thinking_level"):
        NativeGenerationConfig(thinking_level="extreme")


def test_first_turn_request_matches_documented_shape() -> None:
    # Doc: client.interactions.create(model=..., system_instruction=...,
    # input="Hello there") — system instruction is a top-level field, and
    # input is a list of text content parts.
    request = NativeRequest(
        model="gemini-4-neon",
        input=[TextContent(type="text", text="Hello there")],
        system_instruction="You are a cat.",
        generation_config=NativeGenerationConfig(thinking_level="medium"),
    )
    assert request.wire() == {
        "model": "gemini-4-neon",
        "input": [{"type": "text", "text": "Hello there"}],
        "system_instruction": "You are a cat.",
        "stream": True,
        "store": True,
        "generation_config": {"thinking_level": "medium"},
    }


def test_function_result_request_matches_documented_shape() -> None:
    # Doc: create(previous_interaction_id=..., input=[{type: function_result,
    # call_id, name, result: [{type: text, text}]}])
    request = NativeRequest(
        model="gemini-4-neon",
        input=[
            FunctionResult(
                type="function_result",
                name="get_weather",
                call_id="fc_1",
                result=[TextContent(type="text", text="52F and rain")],
            )
        ],
        previous_interaction_id="int_001",
    )
    assert request.wire() == {
        "model": "gemini-4-neon",
        "input": [
            {
                "type": "function_result",
                "name": "get_weather",
                "call_id": "fc_1",
                "result": [{"type": "text", "text": "52F and rain"}],
            }
        ],
        "stream": True,
        "store": True,
        "previous_interaction_id": "int_001",
    }
