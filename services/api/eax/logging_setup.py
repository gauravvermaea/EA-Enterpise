"""JSON logs to standard output, one line per event, with the request ID when there is one."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

from flask import g, has_request_context


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "time": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "container": "api",
        }
        if has_request_context():
            entry["request_id"] = getattr(g, "request_id", None)
            entry["user"] = getattr(g, "username", None)
        if record.exc_info:
            entry["error"] = self.formatException(record.exc_info)
        return json.dumps(entry)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
