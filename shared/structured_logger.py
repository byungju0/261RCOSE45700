from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone

_EXTRA_FIELDS = ("job_id", "scheduled_run_time")


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_record = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
            "service": os.environ.get("SERVICE_NAME", "unknown"),
            "level": record.levelname,
            "correlation_id": getattr(record, "correlation_id", None),
            "message": record.getMessage(),
        }
        for field in _EXTRA_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                log_record[field] = value
        return json.dumps(log_record, ensure_ascii=False, default=str)


def get_logger(name: str | None = None) -> logging.Logger:
    logger = logging.getLogger(name or __name__)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(_JsonFormatter())
        logger.addHandler(handler)
        level = os.environ.get("LOG_LEVEL", "DEBUG").upper()
        logger.setLevel(getattr(logging, level, logging.DEBUG))
        logger.propagate = False
    return logger
