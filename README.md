# [Python-Multipart](https://kludex.github.io/python-multipart/)

[![Build Status](https://github.com/Kludex/python-multipart/workflows/CI/badge.svg)](https://github.com/Kludex/python-multipart/actions)
[![Package version](https://badge.fury.io/py/python-multipart.svg)](https://pypi.python.org/pypi/python-multipart)
[![Supported Python Version](https://img.shields.io/pypi/pyversions/python-multipart.svg?color=%2334D058)](https://pypi.org/project/python-multipart)
[![Discord](https://img.shields.io/discord/1051468649518616576?logo=discord&logoColor=ffffff&color=7389D8&labelColor=6A7EC2)](https://discord.gg/RxKUF5JuHs)

---

`python-multipart` is an Apache2-licensed streaming multipart parser for Python.
Test coverage is currently 100%.

## Why?

Because streaming uploads are awesome for large files.

## Overview

`python-multipart` parses `multipart/form-data`, `octet-stream`, and
query-string request bodies in a streaming fashion: data is fed to the parser
incrementally and callbacks fire as parts are discovered, so large uploads can
be handled without buffering the whole body in memory.

## Capabilities

- **Streaming parsers**: `MultipartParser`, `FormParser`, `OctetStreamParser`,
  `QuerystringParser`, and `BaseParser` for building custom parsers.
- **Convenience helpers**: `parse_form` and `create_form_parser` for the common
  case of reading a form submission into callbacks.
- **Header utilities**: `parse_options_header` for extracting multipart
  boundaries and other parameters from `Content-Type`.
- **Decoders**: `Base64Decoder` and `QuotedPrintableDecoder` for transfer encodings.
- **Callback-driven API**: `on_part_begin`, `on_part_data`, and `on_part_end` run
  incrementally; `on_field` and `on_file` fire after each complete field or file.
- **Zero runtime dependencies**: pure Python, no third-party packages required.

## Installation

```console
pip install python-multipart
```

## Requirements

- Python 3.11+
- No runtime dependencies.
