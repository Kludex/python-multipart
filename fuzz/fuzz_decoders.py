import io
import logging
import sys

logging.disable(logging.CRITICAL)

import atheris
from helpers import EnhancedDataProvider

with atheris.instrument_imports():
    from python_multipart.decoders import Base64Decoder, DecodeError, QuotedPrintableDecoder


def fuzz_base64_decoder(fdp: EnhancedDataProvider) -> None:
    decoder = Base64Decoder(io.BytesIO())
    decoder.write(fdp.ConsumeRandomBytes())
    decoder.finalize()


def fuzz_base64_decoder_chunked(fdp: EnhancedDataProvider) -> None:
    decoder = Base64Decoder(io.BytesIO())
    num_chunks = fdp.ConsumeIntInRange(1, 8)
    body = fdp.ConsumeRandomBytes()
    chunk_size = max(1, (len(body) + num_chunks - 1) // num_chunks)
    for i in range(0, len(body), chunk_size):
        decoder.write(body[i : i + chunk_size])
    decoder.finalize()


def fuzz_quoted_decoder(fdp: EnhancedDataProvider) -> None:
    decoder = QuotedPrintableDecoder(io.BytesIO())
    decoder.write(fdp.ConsumeRandomBytes())
    decoder.finalize()


def fuzz_quoted_decoder_chunked(fdp: EnhancedDataProvider) -> None:
    decoder = QuotedPrintableDecoder(io.BytesIO())
    num_chunks = fdp.ConsumeIntInRange(1, 8)
    body = fdp.ConsumeRandomBytes()
    chunk_size = max(1, (len(body) + num_chunks - 1) // num_chunks)
    for i in range(0, len(body), chunk_size):
        decoder.write(body[i : i + chunk_size])
    decoder.finalize()


def TestOneInput(data: bytes) -> None:
    fdp = EnhancedDataProvider(data)
    targets = [
        fuzz_base64_decoder,
        fuzz_base64_decoder_chunked,
        fuzz_quoted_decoder,
        fuzz_quoted_decoder_chunked,
    ]
    target = fdp.PickValueInList(targets)

    try:
        target(fdp)
    except DecodeError:
        return


def main():
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
