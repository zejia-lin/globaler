import logging


def get_logger(level):
    if __debug__:
        logger = logging.getLogger(__name__)
        logger.setLevel(level)  # Set the logger level to DEBUG
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.NOTSET)
        formatter = logging.Formatter("[%(levelname)s] %(message)s")
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        return logger

    class FakeLogger:
        def debug(self, msg, *args, **kwargs):
            pass

        def info(self, msg, *args, **kwargs):
            pass

        def warning(self, msg, *args, **kwargs):
            pass

        def error(self, msg, *args, **kwargs):
            pass

        def critical(self, msg, *args, **kwargs):
            pass

        def exception(self, msg, *args, **kwargs):
            pass

        def log(self, level, msg, *args, **kwargs):
            pass

    return FakeLogger()
