"""Client ingest quality tracking plugin.

Disabled unless ``SCIPAL_INGEST_TRACKING=1``.
Backend bulk importers must not import this package.
"""

from .store import enabled, ensure_schema
from .routes import build_ingest_tracking_blueprint

__all__ = ["enabled", "ensure_schema", "build_ingest_tracking_blueprint"]
