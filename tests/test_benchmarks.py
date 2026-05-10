from __future__ import annotations

import pytest

from python_multipart import MultipartParser, QuerystringParser

pytestmark = pytest.mark.benchmark

BOUNDARY = b"----python-multipart-benchmark"


def _noop(*_args: object, **_kwargs: object) -> None:
    pass


_MULTIPART_CALLBACKS = {
    "on_part_begin": _noop,
    "on_part_data": _noop,
    "on_part_end": _noop,
    "on_header_field": _noop,
    "on_header_value": _noop,
    "on_header_end": _noop,
    "on_headers_finished": _noop,
    "on_end": _noop,
}

_QUERYSTRING_CALLBACKS = {
    "on_field_start": _noop,
    "on_field_name": _noop,
    "on_field_data": _noop,
    "on_field_end": _noop,
    "on_end": _noop,
}


def _build_multipart_form(parts: list[tuple[bytes, bytes, bytes | None]]) -> bytes:
    chunks: list[bytes] = []
    for name, data, filename in parts:
        chunks.append(b"--" + BOUNDARY + b"\r\n")
        disposition = b'Content-Disposition: form-data; name="' + name + b'"'
        if filename is not None:
            disposition += b'; filename="' + filename + b'"'
        chunks.append(disposition + b"\r\n")
        if filename is not None:
            chunks.append(b"Content-Type: application/octet-stream\r\n")
        chunks.append(b"\r\n")
        chunks.append(data)
        chunks.append(b"\r\n")
    chunks.append(b"--" + BOUNDARY + b"--\r\n")
    return b"".join(chunks)


def _split(data: bytes, chunk_size: int) -> list[bytes]:
    return [data[i : i + chunk_size] for i in range(0, len(data), chunk_size)]


_SMALL_FORM = _build_multipart_form([(b"username", b"alice", None), (b"password", b"hunter2", None)])
_FILE_UPLOAD = _build_multipart_form([(b"upload", b"A" * (2 * 1024 * 1024), b"big.bin")])
_FILE_UPLOAD_CHUNKS = _split(_FILE_UPLOAD, 64 * 1024)
_MIXED_FORM = _build_multipart_form(
    [(b"title", b"hello world", None), (b"description", b"x" * 4096, None), (b"upload", b"A" * 256 * 1024, b"img.bin")]
)
_MIXED_FORM_CHUNKS = _split(_MIXED_FORM, 64 * 1024)
_URLENCODED_SMALL = b"username=alice&password=hunter2&remember=on"
_URLENCODED_LARGE = b"&".join(f"field{i}={'v' * 64}".encode() for i in range(256))
_URLENCODED_LARGE_CHUNKS = _split(_URLENCODED_LARGE, 64)


def test_multipart_small_form() -> None:
    parser = MultipartParser(BOUNDARY, _MULTIPART_CALLBACKS)
    parser.write(_SMALL_FORM)
    parser.finalize()


def test_multipart_file_upload() -> None:
    parser = MultipartParser(BOUNDARY, _MULTIPART_CALLBACKS)
    for chunk in _FILE_UPLOAD_CHUNKS:
        parser.write(chunk)
    parser.finalize()


def test_multipart_mixed_form() -> None:
    parser = MultipartParser(BOUNDARY, _MULTIPART_CALLBACKS)
    for chunk in _MIXED_FORM_CHUNKS:
        parser.write(chunk)
    parser.finalize()


def test_urlencoded_small_form() -> None:
    parser = QuerystringParser(_QUERYSTRING_CALLBACKS)
    parser.write(_URLENCODED_SMALL)
    parser.finalize()


def test_urlencoded_large_form_fragmented() -> None:
    parser = QuerystringParser(_QUERYSTRING_CALLBACKS)
    for chunk in _URLENCODED_LARGE_CHUNKS:
        parser.write(chunk)
    parser.finalize()
