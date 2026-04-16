import logging

from loguru import logger


class InterceptHandler(logging.Handler):
    def emit(self, record):
        logger_opt = logger.opt(depth=6, exception=record.exc_info)
        logger_opt.log(record.levelno, record.getMessage())

    @staticmethod
    def logger_filter(record):
        if has_request_context() and "trace_id" in request.environ.keys():
            trace_id = request.environ.get('trace_id')
            record["extra"].update(
                dict(trace_id=trace_id)
            )
        return record

class LoggerMiddleware:
    @staticmethod
    def init_app(app: Flask, log_name: str = ''):
        logger.remove()
        if log_name is None:
            log_name = 'info.log'
        if config.flask.DEBUG:
            logger.add(sys.stderr)
        app.logger.addHandler(InterceptHandler())
        logging.basicConfig(handlers=[InterceptHandler()], level=config.flask.LOG_LEVEL)