import base64
import binascii

from .exceptions import Base64Error, DecodeError


class Base64Decoder(object):
    def __init__(self, underlying):
        self.cache = bytearray()
        self.underlying = underlying

    def write(self, data):
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
            except Base64Error:
                raise DecodeError('There was an error raised while decoding '
                                  'base64-encoded data.')

            self.underlying.write(decoded)

        # Get the remaining bytes and save in our cache.
        remaining_len = len(data) % 4
        if remaining_len > 0:
            self.cache = data[-remaining_len:]
        else:
            self.cache = b''

        # Return the length of the data to indicate no error.
        return len(data)

    def close(self):
        if hasattr(self.underlying, 'close'):
            self.underlying.close()

    def finalize(self):
        if len(self.cache) > 0:
            raise DecodeError('There are %d bytes remaining in the '
                              'Base64Decoder cache when finalize() is called'
                              % len(self.cache))

        if hasattr(self.underlying, 'finalize'):
            self.underlying.finalize()

    def __repr__(self):
        return "%s(underlying=%r)" % (self.__class__.__name__, self.underlying)


class QuotedPrintableDecoder(object):
    def __init__(self, underlying):
        self.cache = b''
        self.underlying = underlying

    def write(self, data):
        # Prepend any cache info to our data.
        if len(self.cache) > 0:
            data = self.cache + data

        # Since the longest possible escape is 3 characters long, either in
        # the form '=XX' or '=\r\n', we encode up to 3 characters before the
        # end of the string.
        enc, rest = data[:-3], data[-3:]

        # Encode and write, if we have data.
        if len(enc) > 0:
            self.underlying.write(binascii.a2b_qp(enc))

        # Save remaining in cache.
        self.cache = rest
        return len(data)

    def close(self):
        if hasattr(self.underlying, 'close'):
            self.underlying.close()

    def finalize(self):
        # If we have a cache, write and then remove it.
        if len(self.cache) > 0:
            self.underlying.write(binascii.a2b_qp(self.cache))
            self.cache = b''

        # Finalize our underlying stream.
        if hasattr(self.underlying, 'finalize'):
            self.underlying.finalize()

    def __repr__(self):
        return "%s(underlying=%r)" % (self.__class__.__name__, self.underlying)



