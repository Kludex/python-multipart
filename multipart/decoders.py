import base64
import binascii
from io import BufferedWriter

from .exceptions import DecodeError


class Base64Decoder:
    """This object provides an interface to decode a stream of Base64 data.  It
    is instantiated with an "underlying object", and whenever a write()
    operation is performed, it will decode the incoming data as Base64, and
    call write() on the underlying object.  This is primarily used for decoding
    form data encoded as Base64, but can be used for other purposes::

        from multipart.decoders import Base64Decoder
        fd = open("notb64.txt", "wb")
        decoder = Base64Decoder(fd)
        try:
            decoder.write("Zm9vYmFy")       # "foobar" in Base64
            decoder.finalize()
        finally:
            decoder.close()

        # The contents of "notb64.txt" should be "foobar".

    This object will also pass all finalize() and close() calls to the
    underlying object, if the underlying object supports them.

    Note that this class maintains a cache of base64 chunks, so that a write of
    arbitrary size can be performed.  You must call :meth:`finalize` on this
    object after all writes are completed to ensure that all data is flushed
    to the underlying object.

    :param underlying: the underlying object to pass writes to
    """

    def __init__(self, underlying: BufferedWriter):
        self.cache = bytearray()
        self.underlying = underlying

    def write(self, data: bytes) -> int:
        """Takes any input data provided, decodes it as base64, and passes it
        on to the underlying object.  If the data provided is invalid base64
        data, then this method will raise
        a :class:`multipart.exceptions.DecodeError`

        :param data: base64 data to decode
        """

        # Prepend any cache info to our data.
        if len(self.cache) > 0:
            data = self.cache + data

        # Slice off a string that's a multiple of 4.
        decode_len = (len(data) // 4) * 4
        val = data[:decode_len]

        # Decode and write, if we have any.
        if len(val) > 0:
            try:
                decoded = base64.b64decode(val)
            except binascii.Error:
                raise DecodeError("There was an error raised while decoding base64-encoded data.")

            self.underlying.write(decoded)

        # Get the remaining bytes and save in our cache.
        remaining_len = len(data) % 4
        if remaining_len > 0:
            self.cache = data[-remaining_len:]
        else:
            self.cache = b""

        # Return the length of the data to indicate no error.
        return len(data)

    def close(self) -> None:
        """Close this decoder.  If the underlying object has a `close()`
        method, this function will call it.
        """
        if hasattr(self.underlying, "close"):
            self.underlying.close()

    def finalize(self) -> None:
        """Finalize this object.  This should be called when no more data
        should be written to the stream.  This function can raise a
        :class:`multipart.exceptions.DecodeError` if there is some remaining
        data in the cache.

        If the underlying object has a `finalize()` method, this function will
        call it.
        """
        if len(self.cache) > 0:
            raise DecodeError(
                "There are %d bytes remaining in the Base64Decoder cache when finalize() is called" % len(self.cache)
            )

        if hasattr(self.underlying, "finalize"):
            self.underlying.finalize()

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(underlying={self.underlying!r})"


class QuotedPrintableDecoder:
    """This object provides an interface to decode a stream of quoted-printable
    data.  It is instantiated with an "underlying object", in the same manner
    as the :class:`multipart.decoders.Base64Decoder` class.  This class behaves
    in exactly the same way, including maintaining a cache of quoted-printable
    chunks.

    :param underlying: the underlying object to pass writes to
    """

    def __init__(self, underlying: BufferedWriter) -> None:
        self.cache = b""
        self.underlying = underlying

    def write(self, data: bytes) -> int:
        """Takes any input data provided, decodes it as quoted-printable, and
        passes it on to the underlying object.

        :param data: quoted-printable data to decode
        """
        # Prepend any cache info to our data.
        if len(self.cache) > 0:
            data = self.cache + data

        # If the last 2 characters have an '=' sign in it, then we won't be
        # able to decode the encoded value and we'll need to save it for the
        # next decoding step.
        if data[-2:].find(b"=") != -1:
            enc, rest = data[:-2], data[-2:]
        else:
            enc = data
            rest = b""

        # Encode and write, if we have data.
        if len(enc) > 0:
            self.underlying.write(binascii.a2b_qp(enc))

        # Save remaining in cache.
        self.cache = rest
        return len(data)

    def close(self) -> None:
        """Close this decoder.  If the underlying object has a `close()`
        method, this function will call it.
        """
        if hasattr(self.underlying, "close"):
            self.underlying.close()

    def finalize(self) -> None:
        """Finalize this object.  This should be called when no more data
        should be written to the stream.  This function will not raise any
        exceptions, but it may write more data to the underlying object if
        there is data remaining in the cache.

        If the underlying object has a `finalize()` method, this function will
        call it.
        """
        # If we have a cache, write and then remove it.
        if len(self.cache) > 0:  # pragma: no cover
            self.underlying.write(binascii.a2b_qp(self.cache))
            self.cache = b""

        # Finalize our underlying stream.
        if hasattr(self.underlying, "finalize"):
            self.underlying.finalize()

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(underlying={self.underlying!r})"
