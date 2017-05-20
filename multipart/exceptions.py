import binascii

from six import PY3


class FormParserError(ValueError):
    """Base error class for our form parser."""
    pass


class ParseError(FormParserError):
    """This exception (or a subclass) is raised when there is an error while
    parsing something.
    """

    #: This is the offset in the input data chunk (*NOT* the overall stream) in
    #: which the parse error occured.  It will be -1 if not specified.
    offset = -1


class MultipartParseError(ParseError):
    """This is a specific error that is raised when the MultipartParser detects
    an error while parsing.
    """
    pass


class QuerystringParseError(ParseError):
    """This is a specific error that is raised when the QuerystringParser
    detects an error while parsing.
    """
    pass


class DecodeError(ParseError):
    """This exception is raised when there is a decoding error - for example
    with the Base64Decoder or QuotedPrintableDecoder.
    """
    pass


# On Python 3.3, IOError is the same as OSError, so we don't want to inherit
# from both of them.  We handle this case below.
if IOError is not OSError:      # pragma: no cover
    class FileError(FormParserError, IOError, OSError):
        """Exception class for problems with the File class."""
        pass
else:                           # pragma: no cover
    class FileError(FormParserError, OSError):
        """Exception class for problems with the File class."""
        pass

# We check which version of Python we're on to figure out what error we need
# to catch for invalid Base64.
if PY3:                         # pragma: no cover
    Base64Error = binascii.Error
else:                           # pragma: no cover
    Base64Error = TypeError
