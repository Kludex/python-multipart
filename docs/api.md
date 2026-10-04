## URL-encoded field limits

You can bound field count and size while you stream a URL-encoded body.

```python
from python_multipart import FormParser
from python_multipart.multipart import Field

fields: list[Field] = []
parser = FormParser(
    "application/x-www-form-urlencoded",
    on_field=fields.append,
    on_file=None,
    config={"MAX_FIELDS": 2, "MAX_FIELD_SIZE": 9},
)

for chunk in [b"first=one", b"", b"&second=two"]:
    parser.write(chunk)
parser.finalize()

assert [(field.field_name, field.value) for field in fields] == [
    (b"first", b"one"),
    (b"second", b"two"),
]
```

`MAX_FIELDS` limits the number of fields, including duplicate names and fields with empty values.
`MAX_FIELD_SIZE` limits each field's combined raw name/value bytes. It excludes the `=` and `&` separators.
Percent-encoded bytes count before decoding. Both limits accept non-negative numbers.

`FormParser` raises `FormParserError` when a limit is exceeded. It checks field count before assembling a new field
and field size before buffering incoming bytes. A check in `on_field` would be too late to bound memory use.

Both limits default to `float("inf")` to preserve existing behavior. A zero field-count limit rejects every field.
A zero size limit accepts only fields with an empty name and value. These limits apply to
`application/x-www-form-urlencoded` and `application/x-url-encoded`, not multipart forms or file uploads.

Call `finalize()` after the stream ends. Empty chunks do not signal the end of the body.

## API reference

The following reference lists the public classes, functions, and exceptions.

::: python_multipart

::: python_multipart.exceptions
