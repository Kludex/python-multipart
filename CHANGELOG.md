# Changelog

## 0.0.7 (2024-02-03)

* Refactor header option parser to use the standard library instead of a custom RegEx [#75](https://github.com/andrew-d/python-multipart/pull/75).

## 0.0.6 (2023-02-27)

* Migrate package installation to `pyproject.toml` (PEP 621) [#54](https://github.com/andrew-d/python-multipart/pull/54).
* Use yaml.safe_load instead of yaml.load [#46](https://github.com/andrew-d/python-multipart/pull/46).
* Add support for Python 3.11, drop EOL 3.6 [#51](https://github.com/andrew-d/python-multipart/pull/51).
* Add support for Python 3.8-3.10, drop EOL 2.7-3.5 [#42](https://github.com/andrew-d/python-multipart/pull/42).
* `QuerystringParser`: don't raise an AttributeError in `__repr__` [#30](https://github.com/andrew-d/python-multipart/pull/30).
