import io
import sys
from unittest.mock import Mock

import atheris
from helpers import EnhancedDataProvider

with atheris.instrument_imports():
    from multipart.exceptions import FormParserError
    from multipart.multipart import parse_form

on_field = Mock()
on_file = Mock()


def parse_octet_stream(fdp: EnhancedDataProvider) -> None:
    header = {"Content-Type": "application/octet-stream"}
    parse_form(header, io.BytesIO(fdp.ConsumeRandomBytes()), on_field, on_file)


def parse_url_encoded(fdp: EnhancedDataProvider) -> None:
    header = {"Content-Type": "application/x-url-encoded"}
    parse_form(header, io.BytesIO(fdp.ConsumeRandomBytes()), on_field, on_file)


def parse_form_urlencoded(fdp: EnhancedDataProvider) -> None:
    header = {"Content-Type": "application/x-www-form-urlencoded"}
    parse_form(header, io.BytesIO(fdp.ConsumeRandomBytes()), on_field, on_file)


def parse_multipart_form_data(fdp: EnhancedDataProvider) -> None:
    header = {"Content-Type": "multipart/form-data; boundary=--boundary"}
    parse_form(header, io.BytesIO(fdp.ConsumeRandomBytes()), on_field, on_file)


def TestOneInput(data: bytes) -> None:
    fdp = EnhancedDataProvider(data)
    targets = [parse_octet_stream, parse_url_encoded, parse_form_urlencoded, parse_multipart_form_data]
    target = fdp.PickValueInList(targets)

    try:
        target(fdp)
    except FormParserError:
        return


def main():
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
