import io
import sys

import atheris
from helpers import EnhancedDataProvider

with atheris.instrument_imports():
    from python_multipart.decoders import Base64Decoder, DecodeError, QuotedPrintableDecoder


def fuzz_base64_decoder(fdp: EnhancedDataProvider) -> None:
    decoder = Base64Decoder(io.BytesIO())
    decoder.write(fdp.ConsumeRandomBytes())
    decoder.finalize()


def fuzz_quoted_decoder(fdp: EnhancedDataProvider) -> None:
    decoder = QuotedPrintableDecoder(io.BytesIO())
    decoder.write(fdp.ConsumeRandomBytes())
    decoder.finalize()


def TestOneInput(data: bytes) -> None:
    fdp = EnhancedDataProvider(data)
    targets = [fuzz_base64_decoder, fuzz_quoted_decoder]
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
