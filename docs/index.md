# Python-Multipart

Python-Multipart is a streaming multipart parser for Python.

## Quickstart

### Simple Example

The following example shows a quick example of parsing an incoming request body in a simple WSGI application:

```python
import python_multipart

def simple_app(environ, start_response):
    ret = []

    # The following two callbacks just append the name to the return value.
    def on_field(field):
        ret.append(b"Parsed value parameter named: %s" % (field.field_name,))

    def on_file(file):
        ret.append(b"Parsed file parameter named: %s" % (file.field_name,))

    # Create headers object.  We need to convert from WSGI to the actual
    # name of the header, since this library does not assume that you are
    # using WSGI.
    headers = {'Content-Type': environ['CONTENT_TYPE']}
    if 'HTTP_X_FILE_NAME' in environ:
        headers['X-File-Name'] = environ['HTTP_X_FILE_NAME']
    if 'CONTENT_LENGTH' in environ:
        headers['Content-Length'] = environ['CONTENT_LENGTH']

    # Parse the form.
    python_multipart.parse_form(headers, environ['wsgi.input'], on_field, on_file)

    # Return something.
    start_response('200 OK', [('Content-type', 'text/plain')])
    ret.append(b'\n')
    return ret

from wsgiref.simple_server import make_server
from wsgiref.validate import validator

httpd = make_server('', 8123, simple_app)
print("Serving on port 8123...")
httpd.serve_forever()
```

If you test this with curl, you can see that the parser works:

```console
$ curl -ik -F "foo=bar" http://localhost:8123/
HTTP/1.0 200 OK
Date: Sun, 07 Apr 2013 01:40:52 GMT
Server: WSGIServer/0.1 Python/2.7.3
Content-type: text/plain

Parsed value parameter named: foo
```

For a more in-depth example showing how the various parts fit together, check out the next section.

### In-Depth Example

In this section, we’ll build an application that computes the SHA-256 hash of all uploaded files in a streaming manner.

To start, we need a simple WSGI application. We could do this with a framework like Flask, Django, or Tornado, but for now let’s stick to plain WSGI:

```python
import python_multipart

def simple_app(environ, start_response):
    start_response('200 OK', [('Content-type', 'text/plain')])
    return ['Hashes:\n']

from wsgiref.simple_server import make_server
httpd = make_server('', 8123, simple_app)
print("Serving on port 8123...")
httpd.serve_forever()
```

You can run this and check with curl that it works properly:

```console
$ curl -ik http://localhost:8123/
HTTP/1.0 200 OK
Date: Sun, 07 Apr 2013 01:49:03 GMT
Server: WSGIServer/0.1 Python/2.7.3
Content-type: text/plain
Content-Length: 8

Hashes:
```

Good! It works. Now, let’s add some of the code that we need. What we need to do, essentially, is set up the appropriate parser and callbacks so that we can access each portion of the request as it arrives, without needing to store any parts in memory.

We can start off by checking if we need to create the parser at all - if the Content-Type isn’t multipart/form-data, then we’re not going to do anything.

The final code should look like this:

```python
import hashlib
import python_multipart
from python_multipart.multipart import parse_options_header

def simple_app(environ, start_response):
    ret = []

    # Python 2 doesn't have the "nonlocal" keyword from Python 3, so we get
    # around it by setting attributes on a dummy object.
    class g(object):
        hash = None

    # This is called when a new part arrives.  We create a new hash object
    # in this callback.
    def on_part_begin():
        g.hash = hashlib.sha256()

    # We got some data!  Update our hash.
    def on_part_data(data, start, end):
        g.hash.update(data[start:end])

    # Our current part is done, so we can finish the hash.
    def on_part_end():
        ret.append("Part hash: %s" % (g.hash.hexdigest(),))

    # Parse the Content-Type header to get the multipart boundary.
    content_type, params = parse_options_header(environ['CONTENT_TYPE'])
    boundary = params.get(b'boundary')

    # Callbacks dictionary.
    callbacks = {
        'on_part_begin': on_part_begin,
        'on_part_data': on_part_data,
        'on_part_end': on_part_end,
    }

    # Create the parser.
    parser = python_multipart.MultipartParser(boundary, callbacks)

    # The input stream is from the WSGI environ.
    inp = environ['wsgi.input']

    # Feed the parser with data from the request.
    size = int(environ['CONTENT_LENGTH'])
    while size > 0:
        to_read = min(size, 1024 * 1024)
        data = inp.read(to_read)
        parser.write(data)

        size -= len(data)
        if len(data) != to_read:
            break

    start_response('200 OK', [('Content-type', 'text/plain')])
    return ret

from wsgiref.simple_server import make_server
httpd = make_server('', 8123, simple_app)
print("Serving on port 8123...")
httpd.serve_forever()
```

And you can see that this works:

```console
$ echo "Foo bar" > /tmp/test.txt
$ shasum -a 256 /tmp/test.txt
0b64696c0f7ddb9e3435341720988d5455b3b0f0724688f98ec8e6019af3d931  /tmp/test.txt
$ curl -ik -F file=@/tmp/test.txt http://localhost:8123/
HTTP/1.0 200 OK
Date: Sun, 07 Apr 2013 02:09:10 GMT
Server: WSGIServer/0.1 Python/2.7.3
Content-type: text/plain

Hashes:
Part hash: 0b64696c0f7ddb9e3435341720988d5455b3b0f0724688f98ec8e6019af3d931
```


## Historical note

This package used to be accessed via `import multipart`. This still works for
now (with a warning) as long as the Python package `multipart` is not also
installed. If both are installed, you need to use the full PyPI name
`python_multipart` for this package.
