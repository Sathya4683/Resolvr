import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone

#set by the request middleware so every log line inside a request carries the same id
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

#attributes every LogRecord has, we don't want to dump them again as "extra" fields
_STANDARD_ATTRS = set(vars(logging.makeLogRecord({}))) | {"message", "asctime", "taskName", "color_message"}


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str):
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        out = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "service": self.service,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        rid = request_id_var.get()
        if rid:
            out["request_id"] = rid
        #anything passed through extra={...}
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS and not key.startswith("_"):
                out[key] = value
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, default=str)


def setup_logging(service: str, level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service))

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())

    #uvicorn sets up its own handlers, route them through ours instead
    for name in ("uvicorn", "uvicorn.error"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True
    #we log requests ourselves in the middleware (with request id + duration)
    logging.getLogger("uvicorn.access").disabled = True

    for noisy in ("httpx", "httpcore", "urllib3", "sentence_transformers", "apscheduler", "google_genai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
