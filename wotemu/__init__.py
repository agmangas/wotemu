import logging

_logger = logging.getLogger(__name__)
_logger.addHandler(logging.NullHandler())

try:
    import nest_asyncio
    nest_asyncio.apply()
    _logger.info("Patched loop with: %s", nest_asyncio)
except ImportError:
    _logger.info("Using default asyncio loop")
