import json
import logging
from datetime import UTC, datetime


class SafeJSONFormatter(logging.Formatter):
    def format(self, record):
        # Arbitrary messages, arguments and exception strings can contain credentials
        # or customer content. Emit a closed schema, never those free-form values.
        return json.dumps(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "event": getattr(record, "event_code", "runtime_event"),
                "exception_type": record.exc_info[0].__name__ if record.exc_info else None,
            }
        )
