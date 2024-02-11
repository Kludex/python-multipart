# Exceptions

The following are all custom exceptions that python-multipart will raise, for various cases. Each method that will raise an exception will document it in this documentation.

<div class="md-typeset">
    <h2><a href="#multipart.exceptions.DecodeError">DecodeError</a></h2>
</div>

:::multipart.exceptions.DecodeError
This exception is raised when there is a decoding error - for example with the Base64Decoder or QuotedPrintableDecoder.

<div class="md-typeset">
    <h2><a href="#multipart.exceptions.FileError">FileError</a></h2>
</div>

:::multipart.exceptions.FileError
Exception class for problems with the File class.

<div class="md-typeset">
    <h2><a href="#multipart.exceptions.FormParserError">FormParserError</a></h2>
</div>

:::multipart.exceptions.FormParserError
Base error class for our form parser.

<div class="md-typeset">
    <h2><a href="#multipart.exceptions.MultipartParseError">MultipartParseError</a></h2>
</div>

:::multipart.exceptions.MultipartParseError

<div class="md-typeset">
    <h2><a href="#multipart.exceptions.ParseError">ParseError</a></h2>
</div>

:::multipart.exceptions.ParseError

offset = -1
This is the offset in the input data chunk (NOT the overall stream) in which the parse error occured. It will be -1 if not specified.

<div class="md-typeset">
    <h2><a href="#multipart.exceptions.QuerystringParseError">QuerystringParseError</a></h2>
</div>

:::multipart.exceptions.QuerystringParseError
