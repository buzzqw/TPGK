import json
import logging
import sys
from datetime import datetime, timezone


class _JsonFormatter(logging.Formatter):
    def format(self, record):
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        if record.exc_info:
            event["exception"] = self.formatException(record.exc_info)
        return json.dumps(event, ensure_ascii=True)


def configure_logging():
    logger = logging.getLogger("tpgk")
    if logger.handlers:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


def get_logger(name):
    return logging.getLogger(name)
