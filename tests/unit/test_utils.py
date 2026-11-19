"""Tests for home-swe-home's pure utility helpers."""

from __future__ import annotations

import inspect
from typing import Optional, Union

from anima import Service

from home_swe_home.utils.schema import (
    _parse_docstring,
    _python_type_to_json_schema_type,
    service_schema,
)
from home_swe_home.utils.text import decode_text


def test_decode_text_none():
    assert decode_text(None) == ""


def test_decode_text_bytes():
    assert decode_text(b"hello bytes") == "hello bytes"


def test_decode_text_str():
    assert decode_text("already str") == "already str"


def test_python_type_unannotated():
    assert _python_type_to_json_schema_type(inspect.Parameter.empty) == "string"


def test_python_type_optional_unwraps():
    assert _python_type_to_json_schema_type(Optional[str]) == "string"
    assert _python_type_to_json_schema_type(Optional[int]) == "integer"
    assert _python_type_to_json_schema_type(Union[type(None)]) == "string"
    assert _python_type_to_json_schema_type(Union[type(None), str]) == "string"

    class EmptyArgs:
        __origin__ = object
        __args__ = ()

    assert _python_type_to_json_schema_type(EmptyArgs()) == "string"


def test_parse_docstring_args_line_without_colon_skipped():
    desc, params = _parse_docstring(
        """Do something.

        Args:
            name: The name.
            a line without a colon
            age: The age.
        """
    )
    assert desc == "Do something."
    assert params == {"name": "The name.", "age": "The age."}


def test_service_schema_builds_from_call():
    class MyService(Service):
        """Do something.

        Args:
            name: The name.
        """

        def __init__(self, ctx):
            super().__init__(ctx, "my_tool")

        def __call__(self, *, name: str) -> str:
            return name

    schema = service_schema(MyService)
    assert schema["function"]["name"] == "My"
    assert schema["function"]["description"] == "Do something."
    params = schema["function"]["parameters"]
    assert params["properties"]["name"]["type"] == "string"
    assert "name" in params["required"]


def test_service_schema_explicit_name():
    class MyService(Service):
        def __init__(self, ctx):
            super().__init__(ctx, "my_service")

        def __call__(self, *, name: str) -> str:
            return name

    schema = service_schema(MyService, name="my_service")
    assert schema["function"]["name"] == "my_service"


def test_service_schema_name_defaults_strip_service_suffix():
    class DummyService(Service):
        def __init__(self, ctx):
            super().__init__(ctx, "dummy")

        def __call__(self, *, value: str) -> str:
            return value

    schema = service_schema(DummyService)
    assert schema["function"]["name"] == "Dummy"

    class ReadFile(Service):
        def __init__(self, ctx):
            super().__init__(ctx, "read_file")

        def __call__(self, *, path: str) -> str:
            return path

    assert service_schema(ReadFile)["function"]["name"] == "ReadFile"
