class CrawlerError(Exception):
    """Base crawler exception."""


class FetchError(CrawlerError):
    """Request exception."""


class ParseError(CrawlerError):
    """Parse exception."""


class ConfigError(CrawlerError):
    """Configuration exception."""
