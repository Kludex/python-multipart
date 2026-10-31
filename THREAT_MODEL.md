# Threat Model

`python-multipart` parses untrusted `multipart/form-data`, `application/x-www-form-urlencoded`, and
`application/octet-stream` request bodies. This page defines what counts as a vulnerability in the library.

## Scope

**Covered:** code in the `python_multipart` package.

**Not covered:** frameworks built on it, WAFs and proxies, ASGI or WSGI servers, and your application code.

## Trust boundaries

- **Untrusted:** the request body, and the `Content-Type` value passed to the parser.
- **Trusted:** the parser configuration, your callbacks, and the contents of `UPLOAD_DIR`.

## Security goals

- Malformed input raises `FormParserError` or one of its subclasses.
- `MAX_HEADER_COUNT`, `MAX_HEADER_SIZE`, and `MAX_BODY_SIZE` are enforced.
- CPU use stays proportional to the size of the input.
- Uploaded files stay inside `UPLOAD_DIR`.
- Temporary files are deleted when `UPLOAD_DELETE_TMP` is `True`.

## What counts as a vulnerability

- Memory or CPU use out of proportion to the input, or a bypass of a configured limit.
- A file written outside `UPLOAD_DIR`.
- A file or field value exposed to a different request.
- A departure from the specification that changes field names, filenames, or values. These are usually low severity,
  because the impact depends on another parser in front of your application.

## What does not count

Report these as public issues if you think they are bugs.

| Report | Why it is not a vulnerability |
|---|---|
| Another parser reads ambiguous input differently | The specification gives no single correct reading, so neither parser is wrong |
| An exception other than `FormParserError` on malformed input | It fails that one request, and it is fixed as a normal bug |
| Memory use from a large body when `MAX_BODY_SIZE` is not set | The default is unlimited, so you set the limit here or in your server |
| Malicious content in fields, filenames, or file bodies | The library returns what the client sent, and validating it is your job |

## Your responsibilities

- Set body size limits in `MAX_BODY_SIZE` or in your server.
- Treat `name` and `filename` as untrusted, including when you use them in paths or response headers.
- If a WAF or proxy inspects multipart bodies, make it reject ambiguous requests. Do not rely on it as your only
  validation.
- With `UPLOAD_KEEP_FILENAME=True`, an upload replaces any existing file with the same name. Give each user or
  request its own `UPLOAD_DIR`, or leave this option off.

## Reporting

Report vulnerabilities privately through a
[GitHub security advisory](https://github.com/Kludex/python-multipart/security/advisories/new). Include a proof of
concept and the impact. If the impact depends on another parser, also show how `python-multipart` departs from the
specification.
