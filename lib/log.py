import datetime
import logging
import sys


class InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord):
        level = record.levelname
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"{now}|{level}|{record.getMessage()}", file=sys.stderr)
        # print(f"{now}|{level}|{record.getMessage()}", file=sys.stdout)


def init_logging():
    intercept_handler = InterceptHandler()

    loggers = (
        logging.getLogger(name)
        for name in logging.root.manager.loggerDict
        if name.startswith("uvicorn")
    )
    for uvicorn_logger in loggers:
        uvicorn_logger.handlers = []
    logging.getLogger('uvicorn.access').handlers=[intercept_handler]
