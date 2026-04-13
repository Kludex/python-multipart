import logging
import sys

logging.disable(logging.CRITICAL)

import atheris
from helpers import EnhancedDataProvider

with atheris.instrument_imports():
    from python_multipart.multipart import parse_options_header


def fuzz_bytes_input(fdp: EnhancedDataProvider) -> None:
    # WSGI: bytes received from the network, decoded as latin-1 inside the function.
    parse_options_header(fdp.ConsumeRandomBytes())


def fuzz_string_input(fdp: EnhancedDataProvider) -> None:
    # Simulate a caller that already decoded the header value as latin-1.
    raw = fdp.ConsumeRandomBytes()
    parse_options_header(raw.decode("latin-1"))


def fuzz_none_input(fdp: EnhancedDataProvider) -> None:
    parse_options_header(None)


def TestOneInput(data: bytes) -> None:
    fdp = EnhancedDataProvider(data)
    target = fdp.PickValueInList([fuzz_bytes_input, fuzz_string_input, fuzz_none_input])
    target(fdp)


def main():
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
