import logging
import json
import traceback
from datetime import datetime, timezone
import contextvars

# Context variables for structured logging
request_id_var = contextvars.ContextVar("request_id", default=None)
user_id_var = contextvars.ContextVar("user_id", default=None)
query_id_var = contextvars.ContextVar("query_id", default=None)
job_id_var = contextvars.ContextVar("job_id", default=None)

class JSONFormatter(logging.Formatter):
    """
    Formatter that outputs JSON strings after parsing the LogRecord.
    Injects context variables (request_id, user_id, query_id, job_id) automatically.
    """
    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "thread_id": record.thread,
            "thread_name": record.threadName,
        }

        # Inject context variables if they exist
        req_id = request_id_var.get()
        if req_id:
            log_obj["request_id"] = req_id
            
        usr_id = user_id_var.get()
        if usr_id:
            log_obj["user_id"] = usr_id
            
        q_id = query_id_var.get()
        if q_id:
            log_obj["query_id"] = q_id
            
        j_id = job_id_var.get()
        if j_id:
            log_obj["job_id"] = j_id

        # Merge in any extra attributes passed via logging.info("msg", extra={"key": "val"})
        for key, value in record.__dict__.items():
            if key not in ["args", "asctime", "created", "exc_info", "exc_text", "filename",
                           "funcName", "levelname", "levelno", "lineno", "module",
                           "msecs", "message", "msg", "name", "pathname", "process",
                           "processName", "relativeCreated", "stack_info", "thread",
                           "threadName", "taskName"]:
                log_obj[key] = value

        # Exception handling
        if record.exc_info:
            log_obj["exception"] = "".join(traceback.format_exception(*record.exc_info))
            
        return json.dumps(log_obj)

def setup_structured_logging():
    from settings import settings
    level = settings.LOG_LEVEL
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        
    # Add JSON handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(JSONFormatter())
    root_logger.addHandler(console_handler)
    
    # Suppress some noisy third party logs
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    
    return root_logger
