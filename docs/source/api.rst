.. _api:

API
===

.. module:: multipart

This section of the documentation covers all of the public interfaces of
python-multipart.


Parsers
-------

.. currentmodule:: multipart.multipart

.. autoclass:: BaseParser
   :members:

.. autoclass:: OctetStreamParser
   :members:

.. autoclass:: QuerystringParser
   :members:

.. autoclass:: MultipartParser
   :members:


Support Classes
---------------

.. currentmodule:: multipart.multipart

.. autoclass:: Field
   :members:

.. autoclass:: File
   :members:


Decoders
--------

.. currentmodule:: multipart.decoders

.. autoclass:: Base64Decoder
   :members:

.. autoclass:: QuotedPrintableDecoder
   :members:


Exceptions
----------

The following are all custom exceptions that python-multipart will raise, for various cases.  Each method that will raise an exception will document it in this documentation.

.. currentmodule:: multipart.exceptions

.. autoclass:: FormParserError

.. autoclass:: ParseError
   :members:

.. autoclass:: MultipartParseError

.. autoclass:: QuerystringParseError

.. autoclass:: DecodeError

.. autoclass:: FileError

