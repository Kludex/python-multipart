import logging
import sys

logging.disable(logging.CRITICAL)

import atheris
from helpers import EnhancedDataProvider

with atheris.instrument_imports():
    from python_multipart.exceptions import MultipartParseError
    from python_multipart.multipart import MultipartParser


def _noop() -> None:
    pass


def _noop_data(data: bytes, start: int, end: int) -> None:
    pass


def _make_parser(boundary: bytes, max_size: float = float("inf")) -> MultipartParser:
    return MultipartParser(
        boundary,
        callbacks={
            "on_part_begin": _noop,
            "on_part_data": _noop_data,
            "on_part_end": _noop,
            "on_header_begin": _noop,
            "on_header_field": _noop_data,
            "on_header_value": _noop_data,
            "on_header_end": _noop,
            "on_headers_finished": _noop,
            "on_end": _noop,
        },
        max_size=max_size,
    )


def fuzz_single_write(fdp: EnhancedDataProvider) -> None:
    boundary_len = fdp.ConsumeIntInRange(1, max(1, min(70, fdp.remaining_bytes() // 2)))
    boundary = fdp.ConsumeBytes(boundary_len)
    # Drop CR/LF to avoid ValueError from MultipartParser boundary validation.
    boundary = boundary.replace(b"\r", b"-").replace(b"\n", b"-").rstrip(b" \t") or b"B"

    parser = _make_parser(boundary)
    parser.write(fdp.ConsumeRandomBytes())
    parser.finalize()


def fuzz_chunked_write(fdp: EnhancedDataProvider) -> None:
    boundary_len = fdp.ConsumeIntInRange(1, max(1, min(70, fdp.remaining_bytes() // 3)))
    boundary = fdp.ConsumeBytes(boundary_len)
    boundary = boundary.replace(b"\r", b"-").replace(b"\n", b"-").rstrip(b" \t") or b"B"

    num_chunks = fdp.ConsumeIntInRange(1, 16)
    parser = _make_parser(boundary)
    body = fdp.ConsumeRandomBytes()
    if body:
        chunk_size = max(1, (len(body) + num_chunks - 1) // num_chunks)
        for i in range(0, len(body), chunk_size):
            parser.write(body[i : i + chunk_size])
    parser.finalize()


def fuzz_max_size(fdp: EnhancedDataProvider) -> None:
    boundary_len = fdp.ConsumeIntInRange(1, max(1, min(70, fdp.remaining_bytes() // 2)))
    boundary = fdp.ConsumeBytes(boundary_len)
    boundary = boundary.replace(b"\r", b"-").replace(b"\n", b"-").rstrip(b" \t") or b"B"

    max_size = fdp.ConsumeIntInRange(1, 2048)
    parser = _make_parser(boundary, max_size=max_size)
    parser.write(fdp.ConsumeRandomBytes())
    parser.finalize()


def fuzz_invalid_boundary_constructor(fdp: EnhancedDataProvider) -> None:
    boundary_len = fdp.ConsumeIntInRange(0, min(70, fdp.remaining_bytes()))
    boundary = fdp.ConsumeBytes(boundary_len)
    try:
        _make_parser(boundary)
    except ValueError:
        return


def TestOneInput(data: bytes) -> None:
    fdp = EnhancedDataProvider(data)
    targets = [fuzz_single_write, fuzz_chunked_write, fuzz_max_size, fuzz_invalid_boundary_constructor]
    target = fdp.PickValueInList(targets)

    try:
        target(fdp)
    except MultipartParseError:
        return


def main():
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
