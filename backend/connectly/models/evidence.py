"""Indicators, observations and recorded data gaps.

An observation is one value for one place and period, always tied to the dataset it
came from. A community profile is assembled from observations, so every field can show
its source, date, value type and verification status.
"""

from datetime import date

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from connectly.models.base import (
    ADMIN_LEVELS,
    VALUE_TYPES,
    VERIFICATION_STATUSES,
    Base,
    TimestampMixin,
    str_enum,
)
from connectly.models.provenance import Dataset
from connectly.models.sectors import Sector


class Indicator(TimestampMixin, Base):
    """The definition of something measured. Definitions only — values live in Observation."""

    __tablename__ = "indicator"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sector_id: Mapped[int | None] = mapped_column(ForeignKey("sector.id"), index=True)
    unit: Mapped[str] = mapped_column(String(64), nullable=False)
    # True when a larger value means worse access (e.g. distance to nearest clinic).
    higher_is_worse: Mapped[bool | None] = mapped_column(Boolean)
    description: Mapped[str | None] = mapped_column(Text)
    # How the value is obtained, e.g. "derived from GRID3 health facilities".
    method: Mapped[str | None] = mapped_column(Text)

    sector: Mapped[Sector | None] = relationship()


class Observation(TimestampMixin, Base):
    __tablename__ = "observation"
    __table_args__ = (
        Index("ix_observation_lookup", "indicator_id", "geo_level", "geo_id", "period"),
        CheckConstraint("value IS NOT NULL OR value_text IS NOT NULL", name="has_value"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    indicator_id: Mapped[int] = mapped_column(ForeignKey("indicator.id"), nullable=False)
    # Level the value was measured at. Values are never pushed down to smaller areas.
    geo_level: Mapped[str] = mapped_column(
        str_enum(*ADMIN_LEVELS, "settlement", name="observation_geo_level"), nullable=False
    )
    geo_id: Mapped[int] = mapped_column(Integer, nullable=False)
    period: Mapped[str] = mapped_column(String(32), nullable=False)
    value: Mapped[float | None] = mapped_column(Float)
    value_text: Mapped[str | None] = mapped_column(Text)
    margin_of_error: Mapped[float | None] = mapped_column(Float)
    value_type: Mapped[str] = mapped_column(
        str_enum(*VALUE_TYPES, name="value_type"), nullable=False
    )
    verification_status: Mapped[str] = mapped_column(
        str_enum(*VERIFICATION_STATUSES, name="verification_status"),
        default="unverified",
        nullable=False,
    )
    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("dataset.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Page, table or row reference inside the source, for traceability.
    source_reference: Mapped[str | None] = mapped_column(String(512))

    indicator: Mapped[Indicator] = relationship()
    dataset: Mapped[Dataset] = relationship()


class DataGap(TimestampMixin, Base):
    """Data the platform needs but does not have. Shown to users, never hidden."""

    __tablename__ = "data_gap"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    sector_id: Mapped[int | None] = mapped_column(ForeignKey("sector.id"), index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    geographic_scope: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        str_enum("open", "partially_addressed", "resolved", name="data_gap_status"),
        default="open",
        nullable=False,
    )
    candidate_sources: Mapped[str | None] = mapped_column(Text)
    needs_field_verification: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    identified_on: Mapped[date | None] = mapped_column(Date)

    sector: Mapped[Sector | None] = relationship()
