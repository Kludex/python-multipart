import binascii

import pytest

from python_multipart.decoders import QuotedPrintableDecoder


class Sink:
    def __init__(self) -> None:
        self.b = b""

    def write(self, data: bytes) -> int:
        self.b += data
        return len(data)


@pytest.mark.parametrize(
    "data",
    [b"=41=42", b"a=41=42=43z", b"=41=\n=42", b"x=3D=3Dy"],
)
def test_chunked_matches_whole(data: bytes) -> None:
    whole = binascii.a2b_qp(data)
    for i in range(len(data) + 1):
        for j in range(i, len(data) + 1):
            sink = Sink()
            decoder = QuotedPrintableDecoder(sink)
            for part in (data[:i], data[i:j], data[j:]):
                decoder.write(part)
            decoder.finalize()
            assert sink.b == whole, (i, j)
