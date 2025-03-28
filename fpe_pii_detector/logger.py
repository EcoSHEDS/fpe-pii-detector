import logging


def configure_logger(logger, level=logging.DEBUG, format="%(levelname)s - %(message)s"):
    """
    Configure a logger with specified level and format.

    Removes all existing handlers before adding a new one to prevent
    duplicate logging due to a known bug in yolov5 that causes multiple
    handlers to be created.

    Args:
        logger (logging.Logger): Logger object to configure.
        level (int, optional): Logging level. Default is logging.DEBUG.
        format (str, optional): Log message format string.
            Default is '%(levelname)s - %(message)s'.

    Side effects:
        Modifies the provided logger by setting its level and handlers.
    """
    # Remove all existing handlers due to bug in yolov5 that causes multiple handlers to be created
    logger.root.handlers = []
    logger.setLevel(level)
    handler = logging.StreamHandler()
    formatter = logging.Formatter(format)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
