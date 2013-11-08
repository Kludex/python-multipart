.. _api:

API
===

.. module:: multipart

This section of the documentation covers all of the public interfaces of
python-multipart.


Helper Functions
----------------

.. currentmodule:: multipart.multipart

.. autofunction:: parse_form

.. autofunction:: create_form_parser


Main Class
----------

.. currentmodule:: multipart.multipart

.. autoclass:: FormParser
   :members:


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

.. automodule:: multipart.decoders
   :members:


Exceptions
----------

The following are all custom exceptions that python-multipart will raise, for various cases.  Each method that will raise an exception will document it in this documentation.

.. automodule:: multipart.exceptions
   :members:
