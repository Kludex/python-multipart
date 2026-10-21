from __future__ import annotations

import tracemalloc

import pytest

from python_multipart import FormParser, create_form_parser
from python_multipart.exceptions import FormParserError
from python_multipart.multipart import Field


@pytest.mark.parametrize("content_type", ["application/x-www-form-urlencoded", "application/x-url-encoded"])
@pytest.mark.parametrize(
    "chunks",
    [
        [b"first=one&second=two"],
        [b"first=one&sec", b"ond=two"],
        [b"first=one&second=two", b""],
        [b"first=one", b"", b"&second=two", b"", b""],
        [bytes([byte]) for byte in b"first=one&second=two"],
    ],
)
def test_urlencoded_field_limits_accept_exact_boundaries(content_type: str, chunks: list[bytes]) -> None:
    fields: list[Field] = []
    parser = FormParser(content_type, fields.append, None, config={"MAX_FIELDS": 2, "MAX_FIELD_SIZE": 9})
    for chunk in chunks:
        parser.write(chunk)
    parser.finalize()
    assert [(field.field_name, field.value) for field in fields] == [(b"first", b"one"), (b"second", b"two")]


@pytest.mark.parametrize("chunk_size", [1, 2, 1024])
@pytest.mark.parametrize(
    "body,config,message,expected",
    [
        (b"longname", {"MAX_FIELD_SIZE": 3}, "Field exceeded maximum size of 3 bytes", []),
        (b"a=longvalue", {"MAX_FIELD_SIZE": 3}, "Field exceeded maximum size of 3 bytes", []),
        (b"name=value", {"MAX_FIELD_SIZE": 8}, "Field exceeded maximum size of 8 bytes", []),
        (b"x=%41", {"MAX_FIELD_SIZE": 3}, "Field exceeded maximum size of 3 bytes", []),
        (b"a=1&b=12", {"MAX_FIELDS": 1}, "Too many fields", [(b"a", b"1")]),
        (b"a&b", {"MAX_FIELDS": 1}, "Too many fields", [(b"a", None)]),
        (b"=&=", {"MAX_FIELDS": 1}, "Too many fields", [(b"", None)]),
        (b"a=1&a=2", {"MAX_FIELDS": 1}, "Too many fields", [(b"a", b"1")]),
        (b"=", {"MAX_FIELDS": 0}, "Too many fields", []),
        (b"a", {"MAX_FIELD_SIZE": 0}, "Field exceeded maximum size of 0 bytes", []),
        (b"=x", {"MAX_FIELD_SIZE": 0}, "Field exceeded maximum size of 0 bytes", []),
        (b"a=1&b=12", {"MAX_FIELD_SIZE": 2}, "Field exceeded maximum size of 2 bytes", [(b"a", b"1")]),
    ],
)
def test_urlencoded_field_limits_reject_during_write(
    body: bytes, config: dict[str, int], message: str, expected: list[tuple[bytes, bytes | None]], chunk_size: int
) -> None:
    fields: list[Field] = []
    parser = FormParser("application/x-www-form-urlencoded", fields.append, None, config=config)
    with pytest.raises(FormParserError, match=message):
        for offset in range(0, len(body), chunk_size):
            parser.write(body[offset : offset + chunk_size])
    assert [(field.field_name, field.value) for field in fields] == expected


@pytest.mark.parametrize(
    "body,max_fields,expected",
    [(b"", 0, []), (b"&&", 0, []), (b"=", 1, [(b"", None)]), (b"=&=", 2, [(b"", None), (b"", None)])],
)
def test_urlencoded_zero_size_limit(body: bytes, max_fields: int, expected: list[tuple[bytes, None]]) -> None:
    fields: list[Field] = []
    parser = FormParser(
        "application/x-www-form-urlencoded", fields.append, None, config={"MAX_FIELDS": max_fields, "MAX_FIELD_SIZE": 0}
    )
    parser.write(body)
    parser.finalize()
    assert [(field.field_name, field.value) for field in fields] == expected


@pytest.mark.parametrize("key", ["MAX_FIELDS", "MAX_FIELD_SIZE"])
@pytest.mark.parametrize("limit", [-1, float("-inf"), float("nan"), None, "1"])
def test_urlencoded_invalid_field_limit(key: str, limit: int | float | str | None) -> None:
    with pytest.raises(ValueError, match=f"{key} must be a non-negative number"):
        FormParser("application/x-www-form-urlencoded", None, None, config={key: limit})


def test_urlencoded_field_limits_disabled_by_default() -> None:
    fields: list[Field] = []
    parser = FormParser("application/x-www-form-urlencoded", fields.append, None)
    parser.write(b"a=1&" * 1001 + b"large=" + b"x" * (1024 * 1024 + 1))
    parser.finalize()
    assert len(fields) == 1002
    assert fields[-1].field_name == b"large"
    assert fields[-1].value == b"x" * (1024 * 1024 + 1)


@pytest.mark.parametrize("config", [{"MAX_FIELDS": 1}, {"MAX_FIELD_SIZE": 1}])
def test_urlencoded_field_limits_without_callback(config: dict[str, int]) -> None:
    parser = FormParser("application/x-www-form-urlencoded", None, None, config=config)
    with pytest.raises(FormParserError):
        parser.write(b"a=1&b=2")


@pytest.mark.parametrize("body", [b"x" * (2 * 1024 * 1024), b"a=" + b"x" * (2 * 1024 * 1024)])
@pytest.mark.parametrize("config", [{"MAX_FIELDS": 0}, {"MAX_FIELD_SIZE": 2}])
def test_urlencoded_field_limits_reject_before_buffering(body: bytes, config: dict[str, int]) -> None:
    parser = FormParser("application/x-www-form-urlencoded", None, None, config=config)
    tracemalloc.start()
    try:
        with pytest.raises(FormParserError):
            parser.write(body)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < len(body) // 2


def test_create_form_parser_forwards_field_limits() -> None:
    parser = create_form_parser(
        {"Content-Type": b"application/x-www-form-urlencoded"}, None, None, config={"MAX_FIELDS": 0}
    )
    with pytest.raises(FormParserError, match="Too many fields"):
        parser.write(b"a=1")
