#!/usr/bin/env python3
"""http-compliance adapter for python-multipart's public parser API."""

from __future__ import annotations

import base64
import json
import sys
from typing import Any

import python_multipart
from python_multipart.exceptions import MultipartParseError

PROTOCOL = 1
CAPABILITIES = ["multipart.form-data"]


def b64(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def send(message: dict[str, Any]) -> None:
    print(json.dumps(message, separators=(",", ":")), flush=True)


def parse_multipart(message: dict[str, Any]) -> dict[str, Any]:
    boundary = base64.b64decode(message["context"]["boundary"], validate=True)
    chunks = [base64.b64decode(chunk, validate=True) for chunk in message["chunks"]]
    events: list[dict[str, Any]] = []
    header_name = bytearray()
    header_value = bytearray()
    part_started = False
    headers_finished = False
    complete = False

    def on_part_begin() -> None:
        nonlocal part_started, headers_finished
        part_started = True
        headers_finished = False
        events.append({"type": "part_begin"})

    def on_header_field(data: bytes, start: int, end: int) -> None:
        header_name.extend(data[start:end])

    def on_header_value(data: bytes, start: int, end: int) -> None:
        header_value.extend(data[start:end])

    def on_header_end() -> None:
        events.append({"type": "part_header", "name": b64(bytes(header_name)), "value": b64(bytes(header_value))})
        header_name.clear()
        header_value.clear()

    def on_headers_finished() -> None:
        nonlocal headers_finished
        headers_finished = True

    def on_part_data(data: bytes, start: int, end: int) -> None:
        if start != end:
            events.append({"type": "part_data", "data": b64(data[start:end])})

    def on_part_end() -> None:
        events.append({"type": "part_end"})

    def on_end() -> None:
        nonlocal complete
        complete = True
        events.append({"type": "complete"})

    parser = python_multipart.MultipartParser(
        boundary,
        callbacks={
            "on_part_begin": on_part_begin,
            "on_header_field": on_header_field,
            "on_header_value": on_header_value,
            "on_header_end": on_header_end,
            "on_headers_finished": on_headers_finished,
            "on_part_data": on_part_data,
            "on_part_end": on_part_end,
            "on_end": on_end,
        },
    )
    try:
        for chunk in chunks:
            parser.write(chunk)
        parser.finalize()
    except MultipartParseError as error:
        stage = "boundary" if not part_started else ("body" if headers_finished else "part-headers")
        return {
            "op": "result",
            "protocol": PROTOCOL,
            "id": message["id"],
            "status": "rejected",
            "stage": stage,
            "message": str(error),
        }

    if not complete:
        return {
            "op": "result",
            "protocol": PROTOCOL,
            "id": message["id"],
            "status": "incomplete",
            "stage": "body" if headers_finished else ("part-headers" if part_started else "boundary"),
            "message": "end of input before closing multipart delimiter",
        }
    return {"op": "result", "protocol": PROTOCOL, "id": message["id"], "status": "accepted", "events": events}


def main() -> int:
    for line in sys.stdin:
        message = json.loads(line)
        if message.get("op") == "hello":
            send(
                {
                    "op": "ready",
                    "protocol": PROTOCOL,
                    "name": "python-multipart",
                    "version": python_multipart.__version__,
                    "capabilities": CAPABILITIES,
                }
            )
        elif message.get("op") == "case":
            send(parse_multipart(message))
        elif message.get("op") == "shutdown":
            return 0
        else:
            print(f"unexpected operation: {message.get('op')!r}", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
