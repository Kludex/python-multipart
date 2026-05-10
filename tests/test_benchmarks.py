from __future__ import annotations

import string
from typing import TYPE_CHECKING

import pytest

from python_multipart import MultipartParser, QuerystringParser

if TYPE_CHECKING:
    from python_multipart.multipart import MultipartCallbacks, QuerystringCallbacks

pytestmark = pytest.mark.benchmark

BOUNDARY = b"------------------------WqclBHaXe8KIsoSum4zfZ6"
CHUNK_SIZE = 64 * 1024


def _on_event() -> None:
    pass


def _on_data(_data: bytes, _start: int, _end: int) -> None:
    pass


_MULTIPART_CALLBACKS: MultipartCallbacks = {
    "on_part_begin": _on_event,
    "on_part_data": _on_data,
    "on_part_end": _on_event,
    "on_header_field": _on_data,
    "on_header_value": _on_data,
    "on_header_end": _on_event,
    "on_headers_finished": _on_event,
    "on_end": _on_event,
}

_QUERYSTRING_CALLBACKS: QuerystringCallbacks = {
    "on_field_start": _on_event,
    "on_field_name": _on_data,
    "on_field_data": _on_data,
    "on_field_end": _on_event,
    "on_end": _on_event,
}


def _pattern(pat: bytes, size: int) -> bytes:
    return (pat * (size // len(pat) + 1))[:size]


def _build_part(name: bytes, body: bytes, *, filename: bytes | None = None) -> bytes:
    disposition = b'form-data; name="' + name + b'"'
    if filename is not None:
        disposition += b'; filename="' + filename + b'"'
    headers = b"Content-Disposition: " + disposition + b"\r\n"
    if filename is not None:
        headers += b"Content-Type: application/octet-stream\r\n"
    return b"--" + BOUNDARY + b"\r\n" + headers + b"\r\n" + body


def _build_form(parts: list[bytes]) -> bytes:
    return b"\r\n".join(parts) + b"\r\n--" + BOUNDARY + b"--\r\n"


def _split(data: bytes, chunk_size: int = CHUNK_SIZE) -> list[bytes]:
    return [data[i : i + chunk_size] for i in range(0, len(data), chunk_size)]


_PRINTABLE = string.printable.encode("ascii")

_SIMPLE_FORM = _build_form(
    [_build_part(b"email", _pattern(_PRINTABLE, 24)), _build_part(b"password", _pattern(_PRINTABLE, 16))]
)
_LARGE_FORM = _build_form([_build_part(f"field{i}".encode(), _pattern(_PRINTABLE, i)) for i in range(100)])
_FILE_UPLOAD = _build_form([_build_part(b"file", _pattern(_PRINTABLE, 8 * 1024 * 1024), filename=b"file.bin")])
_FILE_UPLOAD_CHUNKS = _split(_FILE_UPLOAD)
_WORSTCASE_BCHAR = _build_form([_build_part(b"file", _pattern(b"Wqcl", 1024 * 1024), filename=b"file.bin")])
_WORSTCASE_BCHAR_CHUNKS = _split(_WORSTCASE_BCHAR)
_URLENCODED_LARGE = b"&".join(f"field{i}={'v' * 64}".encode() for i in range(100))


def _parse_multipart(chunks: list[bytes]) -> None:
    parser = MultipartParser(BOUNDARY, _MULTIPART_CALLBACKS)
    for chunk in chunks:
        parser.write(chunk)
    parser.finalize()


def test_multipart_simple_form() -> None:
    _parse_multipart([_SIMPLE_FORM])


def test_multipart_large_form() -> None:
    _parse_multipart([_LARGE_FORM])


def test_multipart_file_upload() -> None:
    _parse_multipart(_FILE_UPLOAD_CHUNKS)


def test_multipart_worstcase_boundary_chars() -> None:
    _parse_multipart(_WORSTCASE_BCHAR_CHUNKS)


def test_querystring_large_form() -> None:
    parser = QuerystringParser(_QUERYSTRING_CALLBACKS)
    parser.write(_URLENCODED_LARGE)
    parser.finalize()
