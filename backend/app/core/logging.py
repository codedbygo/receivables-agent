"""JSON log lines (US-01-014): one object per line with time, level, logger, message and any extra fields
(request_id, method, path, status, ms). Callers pass ids and codes, never customer text or addresses."""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import TextIO

_STANDARD = set(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        out.update({k: v for k, v in record.__dict__.items() if k not in _STANDARD})
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, default=str, ensure_ascii=False)


def configure(level: str = "INFO", stream: TextIO = sys.stdout) -> None:
    """Route every logger through one JSON handler (worker, mcp; the api uses uvicorn_log.json).
    The MCP server passes stderr: its stdio transport owns stdout."""
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
