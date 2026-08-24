"""Server-Sent Events helpers for streaming HTTP responses."""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, Iterator

from flask import Response, stream_with_context


def sse_response(events: Iterable[Dict[str, Any] | Any]) -> Response:
    def generate() -> Iterator[str]:
        for event in events:
            payload = json.dumps(event, ensure_ascii=False, default=str)
            yield f"data: {payload}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
