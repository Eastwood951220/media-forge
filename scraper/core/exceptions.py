class CrawlerError(Exception):
    """Base crawler exception."""


class FetchError(CrawlerError):
    """Request exception."""


class ParseError(CrawlerError):
    """Parse exception."""


class ConfigError(CrawlerError):
    """Configuration exception."""


class AccessBlockedError(CrawlerError):
    """Raised when a remote site blocks crawler access."""

    def __init__(self, message: str, access_state=None):
        super().__init__(message)
        self.access_state = access_state
