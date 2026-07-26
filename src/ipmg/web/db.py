"""Backwards-compatible alias for :mod:`ipmg.infrastructure.database`.

Scan history is no longer dashboard-specific — the CLI writes to the same
store — so the implementation now lives in the infrastructure layer.
"""

from ipmg.infrastructure.database import DEFAULT_DB_PATH, Database

__all__ = ["DEFAULT_DB_PATH", "Database"]
