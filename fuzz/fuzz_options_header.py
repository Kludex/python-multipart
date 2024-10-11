import sys

import atheris
from helpers import EnhancedDataProvider

with atheris.instrument_imports():
    from python_multipart.multipart import parse_options_header


def TestOneInput(data: bytes) -> None:
    fdp = EnhancedDataProvider(data)
    try:
        parse_options_header(fdp.ConsumeRandomBytes())
    except AssertionError:
        return
    except TypeError:
        return


def main():
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
