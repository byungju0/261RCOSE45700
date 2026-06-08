from __future__ import annotations


class TrackerBaseException(Exception):
    def __init__(self, message: str, correlation_id: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.correlation_id = correlation_id

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(message={self.message!r}, correlation_id={self.correlation_id!r})"


class CrawlerException(TrackerBaseException):
    def __init__(
        self,
        message: str,
        correlation_id: str | None = None,
        *,
        crawl_stats: dict | None = None,
    ) -> None:
        super().__init__(message, correlation_id)
        self.crawl_stats = crawl_stats or {}


class DetectionException(TrackerBaseException):
    pass


class ApiException(TrackerBaseException):
    pass
