import logging


def get_logger(level, name=__name__):
    if __debug__:
        logger = logging.getLogger(name)
        logger.setLevel(level)
        
        if not logger.handlers:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.NOTSET)
            formatter = logging.Formatter("%(levelname)s %(asctime)s %(filename)s:%(lineno)d] %(message)s")
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
