import logging
import sys

logging.disable(logging.CRITICAL)

import atheris
from helpers import EnhancedDataProvider

with atheris.instrument_imports():
    from python_multipart.exceptions import QuerystringParseError
    from python_multipart.multipart import QuerystringParser


def _noop_data(data: bytes, start: int, end: int) -> None:
    pass


def _noop() -> None:
    pass


def fuzz_single_write(fdp: EnhancedDataProvider) -> None:
    strict = fdp.ConsumeBool()
    parser = QuerystringParser(
        callbacks={
            "on_field_start": _noop,
            "on_field_name": _noop_data,
            "on_field_data": _noop_data,
            "on_field_end": _noop,
            "on_end": _noop,
        },
        strict_parsing=strict,
    )
    parser.write(fdp.ConsumeRandomBytes())
    parser.finalize()


def fuzz_chunked_write(fdp: EnhancedDataProvider) -> None:
    strict = fdp.ConsumeBool()
    num_chunks = fdp.ConsumeIntInRange(1, 8)
    parser = QuerystringParser(
        callbacks={
            "on_field_start": _noop,
            "on_field_name": _noop_data,
            "on_field_data": _noop_data,
            "on_field_end": _noop,
            "on_end": _noop,
        },
        strict_parsing=strict,
    )
    body = fdp.ConsumeRandomBytes()
    chunk_size = max(1, (len(body) + num_chunks - 1) // num_chunks)
    for i in range(0, len(body), chunk_size):
        parser.write(body[i : i + chunk_size])
    parser.finalize()


def fuzz_max_size(fdp: EnhancedDataProvider) -> None:
    body = fdp.ConsumeRandomBytes()
    body_len = max(1, len(body))
    # Pick max_size anywhere from 1 byte up to 2× the body — covers both
    # "truncate heavily" and "allow everything through" branches.
    max_size = fdp.ConsumeIntInRange(1, body_len * 2)
    parser = QuerystringParser(
        callbacks={
            "on_field_start": _noop,
            "on_field_name": _noop_data,
            "on_field_data": _noop_data,
            "on_field_end": _noop,
            "on_end": _noop,
        },
        max_size=max_size,
    )
    parser.write(body)
    parser.finalize()


def TestOneInput(data: bytes) -> None:
    fdp = EnhancedDataProvider(data)
    targets = [fuzz_single_write, fuzz_chunked_write, fuzz_max_size]
    target = fdp.PickValueInList(targets)

    try:
        target(fdp)
    except QuerystringParseError:
        return


def main():
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
