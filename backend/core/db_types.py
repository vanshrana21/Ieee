"""
Dialect-aware database types.
Provides PostgreSQL JSONB when available,
falls back to generic JSON for SQLite.
"""

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import TypeDecorator
from sqlalchemy.engine import Dialect


class UniversalJSON(TypeDecorator):
    """
    Uses JSONB for PostgreSQL.
    Uses JSON for SQLite and others.
    """
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(JSON())
