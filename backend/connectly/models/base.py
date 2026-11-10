"""Declarative base and shared vocabularies.

Vocabularies are stored as constrained strings rather than native Postgres enums so
new values can be added with a simple migration.
"""

from datetime import datetime

from sqlalchemy import DateTime, Enum, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


def str_enum(*values: str, name: str) -> Enum:
    """A string column restricted to `values` by a CHECK constraint."""
    return Enum(*values, name=name, native_enum=False, create_constraint=True, length=32)


# Geographic levels in the administrative hierarchy, from largest to smallest.
ADMIN_LEVELS = ("country", "state", "lga", "ward")
PARENT_LEVEL = {"state": "country", "lga": "state", "ward": "lga"}

# How a value was produced. Mirrors the brief's distinction between verified facts,
# estimates, assumptions and AI-generated content.
VALUE_TYPES = ("measured", "estimated", "modelled", "derived", "assumed", "ai_generated")

# How far a record has been checked.
VERIFICATION_STATUSES = (
    "unverified",
    "source_verified",
    "field_verified",
    "disputed",
    "retired",
)
