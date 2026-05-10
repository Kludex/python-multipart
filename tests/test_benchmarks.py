from __future__ import annotations

import string
from collections.abc import Iterator
from typing import TYPE_CHECKING

import pytest

from python_multipart import MultipartParser, QuerystringParser

if TYPE_CHECKING:
    from python_multipart.multipart import MultipartCallbacks, QuerystringCallbacks

pytestmark = pytest.mark.benchmark

BOUNDARY = b"------------------------WqclBHaXe8KIsoSum4zfZ6"
CHUNK_SIZE = 64 * 1024


def on_event() -> None:
    pass


def on_data(_data: bytes, _start: int, _end: int) -> None:
    pass


MULTIPART_CALLBACKS: MultipartCallbacks = {
    "on_part_begin": on_event,
    "on_part_data": on_data,
    "on_part_end": on_event,
    "on_header_field": on_data,
    "on_header_value": on_data,
    "on_header_end": on_event,
    "on_headers_finished": on_event,
    "on_end": on_event,
}

QUERYSTRING_CALLBACKS: QuerystringCallbacks = {
    "on_field_start": on_event,
    "on_field_name": on_data,
    "on_field_data": on_data,
    "on_field_end": on_event,
    "on_end": on_event,
}


def pattern(pat: bytes, size: int) -> bytes:
    return (pat * (size // len(pat) + 1))[:size]


def build_part(name: bytes, body: bytes, *, filename: bytes | None = None) -> bytes:
    disposition = b'form-data; name="' + name + b'"'
    if filename is not None:
        disposition += b'; filename="' + filename + b'"'
    headers = b"Content-Disposition: " + disposition + b"\r\n"
    if filename is not None:
        headers += b"Content-Type: application/octet-stream\r\n"
    return b"--" + BOUNDARY + b"\r\n" + headers + b"\r\n" + body


def build_form(parts: list[bytes]) -> bytes:
    return b"\r\n".join(parts) + b"\r\n--" + BOUNDARY + b"--\r\n"


def split(data: bytes, chunk_size: int = CHUNK_SIZE) -> list[bytes]:
    return [data[i : i + chunk_size] for i in range(0, len(data), chunk_size)]


PRINTABLE = string.printable.encode("ascii")

SIMPLE_FORM = build_form(
    [build_part(b"email", pattern(PRINTABLE, 24)), build_part(b"password", pattern(PRINTABLE, 16))]
)
LARGE_FORM = build_form([build_part(f"field{i}".encode(), pattern(PRINTABLE, i)) for i in range(100)])
FILE_UPLOAD = build_form([build_part(b"file", pattern(PRINTABLE, 8 * 1024 * 1024), filename=b"file.bin")])
FILE_UPLOAD_CHUNKS = split(FILE_UPLOAD)
WORSTCASE_BCHAR = build_form([build_part(b"file", pattern(BOUNDARY[:1], 1024 * 1024), filename=b"file.bin")])
WORSTCASE_BCHAR_CHUNKS = split(WORSTCASE_BCHAR)

LONG_BOUNDARY = b"-" * 16 + b"x" * (16 * 1024 - 16)
LONG_BOUNDARY_BODY = (
    b"--"
    + LONG_BOUNDARY
    + b"\r\n"
    + b'Content-Disposition: form-data; name="file"; filename="file.bin"\r\n'
    + b"Content-Type: application/octet-stream\r\n\r\n"
    + pattern(PRINTABLE, 2 * 1024 * 1024)
    + b"\r\n--"
    + LONG_BOUNDARY
    + b"--\r\n"
)
LONG_BOUNDARY_CHUNKS = split(LONG_BOUNDARY_BODY, 16 * 1024)

URLENCODED_LARGE = b"&".join(f"field{i}={'v' * 64}".encode() for i in range(100))


@pytest.fixture
def multipart_parser() -> Iterator[MultipartParser]:
    parser = MultipartParser(BOUNDARY, MULTIPART_CALLBACKS)
    yield parser
    parser.finalize()


@pytest.fixture
def long_boundary_parser() -> Iterator[MultipartParser]:
    parser = MultipartParser(LONG_BOUNDARY, MULTIPART_CALLBACKS)
    yield parser
    parser.finalize()


@pytest.fixture
def querystring_parser() -> Iterator[QuerystringParser]:
    parser = QuerystringParser(QUERYSTRING_CALLBACKS)
    yield parser
    parser.finalize()


def test_multipart_simple_form(multipart_parser: MultipartParser) -> None:
    multipart_parser.write(SIMPLE_FORM)


def test_multipart_large_form(multipart_parser: MultipartParser) -> None:
    multipart_parser.write(LARGE_FORM)


def test_multipart_file_upload(multipart_parser: MultipartParser) -> None:
    for chunk in FILE_UPLOAD_CHUNKS:
        multipart_parser.write(chunk)


def test_multipart_worstcase_boundary_chars(multipart_parser: MultipartParser) -> None:
    for chunk in WORSTCASE_BCHAR_CHUNKS:
        multipart_parser.write(chunk)


def test_multipart_long_boundary(long_boundary_parser: MultipartParser) -> None:
    for chunk in LONG_BOUNDARY_CHUNKS:
        long_boundary_parser.write(chunk)


def test_querystring_large_form(querystring_parser: QuerystringParser) -> None:
    querystring_parser.write(URLENCODED_LARGE)
