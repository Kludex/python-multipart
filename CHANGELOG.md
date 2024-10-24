# Changelog

## 0.0.14 (2024-10-24)

* Fix import scheme for `multipart` module ([#168](https://github.com/user/repo/issues/168)).

## 0.0.13 (2024-10-20)

* Rename import to `python_multipart` [#166](https://github.com/Kludex/python-multipart/pull/166).

## 0.0.12 (2024-09-29)

* Improve error message when boundary character does not match [#124](https://github.com/Kludex/python-multipart/pull/124).
* Add mypy strict typing [#140](https://github.com/Kludex/python-multipart/pull/140).
* Enforce 100% coverage [#159](https://github.com/Kludex/python-multipart/pull/159).

## 0.0.11 (2024-09-28)

* Improve performance, especially in data with many CR-LF [#137](https://github.com/Kludex/python-multipart/pull/137).
* Handle invalid CRLF in header name [#141](https://github.com/Kludex/python-multipart/pull/141).

## 0.0.10 (2024-09-21)

* Support `on_header_begin` [#103](https://github.com/Kludex/python-multipart/pull/103).
* Improve type hints on `FormParser` [#104](https://github.com/Kludex/python-multipart/pull/104).
* Fix `OnFileCallback` type [#106](https://github.com/Kludex/python-multipart/pull/106).
* Improve type hints [#110](https://github.com/Kludex/python-multipart/pull/110).
* Improve type hints on `File` [#111](https://github.com/Kludex/python-multipart/pull/111).
* Add type hint to helper functions [#112](https://github.com/Kludex/python-multipart/pull/112).
* Minor fix for Field.__repr__ [#114](https://github.com/Kludex/python-multipart/pull/114).
* Fix use of chunk_size parameter [#136](https://github.com/Kludex/python-multipart/pull/136).
* Allow digits and valid token chars in headers [#134](https://github.com/Kludex/python-multipart/pull/134).
* Fix headers being carried between parts [#135](https://github.com/Kludex/python-multipart/pull/135).

## 0.0.9 (2024-02-10)

* Add support for Python 3.12 [#85](https://github.com/Kludex/python-multipart/pull/85).
* Drop support for Python 3.7 [#95](https://github.com/Kludex/python-multipart/pull/95).
* Add `MultipartState(IntEnum)` [#96](https://github.com/Kludex/python-multipart/pull/96).
* Add `QuerystringState` [#97](https://github.com/Kludex/python-multipart/pull/97).
* Add `TypedDict` callbacks [#98](https://github.com/Kludex/python-multipart/pull/98).
* Add config `TypedDict`s [#99](https://github.com/Kludex/python-multipart/pull/99).

## 0.0.8 (2024-02-09)

* Check if Message.get_params return 3-tuple instead of str on parse_options_header [#79](https://github.com/Kludex/python-multipart/pull/79).
* Cleanup unused regex patterns [#82](https://github.com/Kludex/python-multipart/pull/82).

## 0.0.7 (2024-02-03)

* Refactor header option parser to use the standard library instead of a custom RegEx [#75](https://github.com/andrew-d/python-multipart/pull/75).

## 0.0.6 (2023-02-27)

* Migrate package installation to `pyproject.toml` (PEP 621) [#54](https://github.com/andrew-d/python-multipart/pull/54).
* Use yaml.safe_load instead of yaml.load [#46](https://github.com/andrew-d/python-multipart/pull/46).
* Add support for Python 3.11, drop EOL 3.6 [#51](https://github.com/andrew-d/python-multipart/pull/51).
* Add support for Python 3.8-3.10, drop EOL 2.7-3.5 [#42](https://github.com/andrew-d/python-multipart/pull/42).
* `QuerystringParser`: don't raise an AttributeError in `__repr__` [#30](https://github.com/andrew-d/python-multipart/pull/30).
