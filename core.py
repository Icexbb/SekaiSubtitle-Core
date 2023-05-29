import sys

from uvicorn import run
from uvicorn.config import LOGGING_CONFIG

from app import app

VERSION = 'v1.0.230529'

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("-v", "--version", required=False, action="store_true")
    parser.add_argument("-p", "--port", required=False, default=50000, type=int)
    args = parser.parse_args()
    if args.version:
        print(VERSION, file=sys.stdout)
    else:
        LOGGING_CONFIG["formatters"]["access"][
            "fmt"] = '%(asctime)s %(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s'
        LOGGING_CONFIG["formatters"]["default"]["fmt"] = "%(asctime)s %(levelprefix)s %(message)s"

        date_fmt = "%Y-%m-%d %H:%M:%S"
        LOGGING_CONFIG["formatters"]["default"]["datefmt"] = date_fmt
        LOGGING_CONFIG["formatters"]["access"]["datefmt"] = date_fmt
        LOGGING_CONFIG["handlers"]["default"]["stream"] = "ext://sys.stdout"

        run(app, log_config=LOGGING_CONFIG, host="localhost", port=args.port)
