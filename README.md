# Python-Multipart

[![CI](https://github.com/Kludex/python-multipart/actions/workflows/main.yml/badge.svg)](https://github.com/Kludex/python-multipart/actions/workflows/main.yml)
[![PyPI](https://img.shields.io/pypi/v/python-multipart.svg)](https://pypi.org/project/python-multipart)
[![Python versions](https://img.shields.io/pypi/pyversions/python-multipart.svg)](https://pypi.org/project/python-multipart)
[![Discord](https://img.shields.io/discord/1051468649518616576?logo=discord&logoColor=ffffff&color=7389D8&labelColor=6A7EC2)](https://discord.gg/RxKUF5JuHs)

Python-Multipart reads the data that a web browser sends when someone submits a form or uploads a file.

```console
pip install python-multipart
```

It powers file uploads in [Starlette](https://starlette.dev) and [FastAPI](https://fastapi.tiangolo.com).

## What problem does it solve?

### A form sends data

When you fill in a form on a website and click "Submit", your browser sends the data to a server.
The server is a program, maybe written in Python, that has to read that data and make sense of it.

### Files need a special format

A form with only text, like a username, is sent as one short line: `username=alice`.

A form with a file is different. A file can contain anything, even text that looks like `username=alice`.
So the browser uses a format called `multipart/form-data`. It splits the request into **parts**, one per form field, separated by a **boundary**: a marker string the browser picks.

This is what the server receives when you send a username and a file called `cat.txt`:

```text
--boundary
Content-Disposition: form-data; name="username"

alice
--boundary
Content-Disposition: form-data; name="avatar"; filename="cat.txt"
Content-Type: text/plain

meow
--boundary--
```

Each part has some headers (the field name, the file name) and then the content.
A **parser** is the code that turns this text back into fields and files. Python-Multipart is that parser.

### Big files do not fit in memory

An upload can be a 5 GB video. If the server reads the whole request before it starts working, it needs 5 GB of memory, per upload.

Python-Multipart is a **streaming** parser. You give it the request a small piece (a **chunk**) at a time, and it tells you what it found as soon as it finds it. The full request never has to be in memory.

## Usage

### Parse a whole form

```python
from io import BytesIO

from python_multipart import parse_form

body = (
    b"--boundary\r\n"
    b'Content-Disposition: form-data; name="username"\r\n'
    b"\r\n"
    b"alice\r\n"
    b"--boundary\r\n"
    b'Content-Disposition: form-data; name="avatar"; filename="cat.txt"\r\n'
    b"Content-Type: text/plain\r\n"
    b"\r\n"
    b"meow\r\n"
    b"--boundary--\r\n"
)
headers = {"Content-Type": "multipart/form-data; boundary=boundary"}


def on_field(field):
    print("Field:", field.field_name, "=", field.value)


def on_file(file):
    file.file_object.seek(0)
    print("File:", file.field_name, file.file_name, file.file_object.read())


parse_form(headers, BytesIO(body), on_field, on_file)
```

Output:

```text
Field: b'username' = b'alice'
File: b'avatar' b'cat.txt' b'meow'
```

`parse_form` reads the body in chunks and calls your functions:

- `on_field` runs for every text field.
- `on_file` runs for every uploaded file.

Small files stay in memory. Once a file grows past 1 MiB, it is moved to a temporary file on disk, so a large upload does not fill up your memory.

> **Real servers do not use `BytesIO`.** In a real application, the body comes from the network. Any object with a `read()` method that returns `bytes` works.

### Handle each chunk yourself

`parse_form` still saves every file somewhere. When you want full control, for example to send an upload straight to cloud storage, use `MultipartParser`:

```python
from python_multipart import MultipartParser

chunks = [
    b"--boundary\r\n",
    b'Content-Disposition: form-data; name="avatar"; filename="cat.txt"\r\n\r\n',
    b"me",
    b"ow\r\n--boundary--\r\n",
]


def on_part_data(data, start, end):
    print("Got a piece of the file:", data[start:end])


parser = MultipartParser("boundary", callbacks={"on_part_data": on_part_data})
for chunk in chunks:
    parser.write(chunk)
parser.finalize()
```

Output:

```text
Got a piece of the file: b'me'
Got a piece of the file: b'ow'
```

The file arrived in two chunks, and you saw each one as it arrived. Nothing was stored.

Instead of copying data, the parser passes you a buffer plus `start` and `end` positions that mark the part you care about.

## Learn more

- [Documentation](https://kludex.github.io/python-multipart/)
- [API reference](https://kludex.github.io/python-multipart/api/)
- [Changelog](https://github.com/Kludex/python-multipart/blob/main/CHANGELOG.md)

## License

Apache 2.0. See [LICENSE.txt](LICENSE.txt).
