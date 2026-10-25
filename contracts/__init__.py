"""Response/error contracts shared by HTTP, MCP and CLI boundaries.

Import from here rather than the submodules:

    from contracts import ok, fail, AppError, ErrorKind
"""

from .envelope import SCHEMA_VERSION, fail, is_ok, ok
from .errors import (
    AppError,
    Conflict,
    ErrorKind,
    Forbidden,
    InternalError,
    InvalidInput,
    NotFound,
    RateLimited,
    STATUS_BY_KIND,
    UpstreamError,
    UpstreamTimeout,
    from_exception,
)

__all__ = [
    "SCHEMA_VERSION",
    "ok",
    "fail",
    "is_ok",
    "AppError",
    "ErrorKind",
    "STATUS_BY_KIND",
    "from_exception",
    "InvalidInput",
    "NotFound",
    "Conflict",
    "Forbidden",
    "RateLimited",
    "UpstreamError",
    "UpstreamTimeout",
    "InternalError",
]
