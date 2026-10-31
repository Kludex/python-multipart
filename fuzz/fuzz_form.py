import io
import logging
import sys

logging.disable(logging.CRITICAL)

import atheris
from helpers import EnhancedDataProvider

with atheris.instrument_imports():
    from python_multipart.exceptions import FormParserError
    from python_multipart.multipart import parse_form


def _on_field(field) -> None:
    pass


def _on_file(file) -> None:
    pass


def parse_octet_stream(fdp: EnhancedDataProvider) -> None:
    header = {"Content-Type": "application/octet-stream"}
    parse_form(header, io.BytesIO(fdp.ConsumeRandomBytes()), _on_field, _on_file)


def parse_url_encoded(fdp: EnhancedDataProvider) -> None:
    ct = fdp.PickValueInList(["application/x-url-encoded", "application/x-www-form-urlencoded"])
    header = {"Content-Type": ct}
    parse_form(header, io.BytesIO(fdp.ConsumeRandomBytes()), _on_field, _on_file)


def parse_multipart_raw(fdp: EnhancedDataProvider) -> None:
    # Boundary: 1-70 bytes, no CR/LF (RFC 2046 constraint kept to avoid ValueError).
    boundary_len = fdp.ConsumeIntInRange(1, max(1, min(70, fdp.remaining_bytes() // 2)))
    boundary = fdp.ConsumeBytes(boundary_len)
    boundary = boundary.replace(b"\r", b"-").replace(b"\n", b"-").rstrip(b" \t") or b"B"
    header = {"Content-Type": "multipart/form-data; boundary=" + boundary.decode("latin-1")}
    body = fdp.ConsumeRandomBytes()
    parse_form(header, io.BytesIO(body), _on_field, _on_file)


def parse_multipart_with_content_length(fdp: EnhancedDataProvider) -> None:
    boundary = b"boundary"
    content_length = fdp.ConsumeIntInRange(0, 1024)
    header = {
        "Content-Type": "multipart/form-data; boundary=boundary",
        "Content-Length": str(content_length),
    }
    body = fdp.ConsumeRandomBytes()
    parse_form(header, io.BytesIO(body), _on_field, _on_file)


def parse_form_urlencoded_chunked(fdp: EnhancedDataProvider) -> None:
    from python_multipart.multipart import create_form_parser

    num_chunks = fdp.ConsumeIntInRange(1, 8)
    header = {"Content-Type": "application/x-www-form-urlencoded"}
    parser = create_form_parser(header, _on_field, _on_file)
    body = fdp.ConsumeRandomBytes()
    chunk_size = max(1, (len(body) + num_chunks - 1) // num_chunks)
    for i in range(0, len(body), chunk_size):
        parser.write(body[i : i + chunk_size])
    parser.finalize()

def TestOneInput(data: bytes) -> None:
    fdp = EnhancedDataProvider(data)
    targets = [
        parse_octet_stream,
        parse_url_encoded,
        parse_multipart_raw,
        parse_multipart_with_content_length,
        parse_form_urlencoded_chunked,
    ]
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
