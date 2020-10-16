import logging

_logger = logging.getLogger(__name__)
_logger.addHandler(logging.NullHandler())

try:
    import pandas
    pandas.set_option("display.max_columns", None)
except ImportError:
    pass
