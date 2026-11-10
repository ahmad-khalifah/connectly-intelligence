"""Community-level records: settlements, facilities and qualitative claims.

A "community" in Connectly is a place people live: a settlement where settlement data is
loaded, otherwise the ward (the smallest administrative unit). Settlements and facilities
are linked to their ward, LGA and state by point-in-polygon at load time, so filters do
not depend on name matching.
"""

from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import true as sa_true
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from connectly.models.base import (
    VALUE_TYPES,
    VERIFICATION_STATUSES,
    Base,
    TimestampMixin,
    str_enum,
)
from connectly.models.provenance import Dataset

# What a facility is. Subtypes are free text from the source (e.g. "Primary Health Centre").
FACILITY_KINDS = (
    "health",
    "education",
    "financial",
    "telecom",
    "energy",
    "market",
    "transport",
    "agriculture",
    "community",
    "other",
)

CLAIM_SUBJECTS = ("admin_area", "settlement")


class AdminLinkMixin:
    """Denormalised links to the administrative hierarchy, set by point-in-polygon."""

    ward_id: Mapped[int | None] = mapped_column(
        ForeignKey("admin_area.id", ondelete="SET NULL"), index=True
    )
    lga_id: Mapped[int | None] = mapped_column(
        ForeignKey("admin_area.id", ondelete="SET NULL"), index=True
    )
    state_id: Mapped[int | None] = mapped_column(
        ForeignKey("admin_area.id", ondelete="SET NULL"), index=True
    )


class Settlement(TimestampMixin, AdminLinkMixin, Base):
    __tablename__ = "settlement"
    __table_args__ = (
        UniqueConstraint("dataset_id", "source_code", name="uq_settlement_dataset_code"),
        Index("ix_settlement_name", "name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(String(255))  # many extents are unnamed
    source_name: Mapped[str | None] = mapped_column(String(255))
    source_code: Mapped[str] = mapped_column(String(128), nullable=False)
    # None for settlements added by a researcher (their source is in `source_note`).
    dataset_id: Mapped[int | None] = mapped_column(
        ForeignKey("dataset.id", ondelete="CASCADE"), index=True
    )
    settlement_type: Mapped[str | None] = mapped_column(String(64))
    point = mapped_column(Geometry("POINT", srid=4326, spatial_index=True), nullable=False)
    extent = mapped_column(Geometry("MULTIPOLYGON", srid=4326, spatial_index=True))
    verification_status: Mapped[str] = mapped_column(
        str_enum(*VERIFICATION_STATUSES, name="settlement_verification"),
        default="unverified",
        server_default="unverified",
        nullable=False,
    )
    source_note: Mapped[str | None] = mapped_column(Text)
    attributes: Mapped[dict | None] = mapped_column(JSONB)

    dataset: Mapped[Dataset | None] = relationship()


class Facility(TimestampMixin, AdminLinkMixin, Base):
    """Point infrastructure: health facilities, schools, banks and agents, cell sites..."""

    __tablename__ = "facility"
    __table_args__ = (
        UniqueConstraint("dataset_id", "source_code", name="uq_facility_dataset_code"),
        Index("ix_facility_kind", "kind", "subtype"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(str_enum(*FACILITY_KINDS, name="facility_kind"))
    subtype: Mapped[str | None] = mapped_column(String(128))
    name: Mapped[str | None] = mapped_column(String(255))
    source_code: Mapped[str] = mapped_column(String(128), nullable=False)
    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("dataset.id", ondelete="CASCADE"), nullable=False, index=True
    )
    geom = mapped_column(Geometry("POINT", srid=4326, spatial_index=True), nullable=False)
    # As published, e.g. "Functional" / "Not functional". None when the source has no status.
    operational_status: Mapped[str | None] = mapped_column(String(64))
    ownership: Mapped[str | None] = mapped_column(String(64))
    verification_status: Mapped[str] = mapped_column(
        str_enum(*VERIFICATION_STATUSES, name="facility_verification"),
        default="unverified",
        server_default="unverified",
        nullable=False,
    )
    attributes: Mapped[dict | None] = mapped_column(JSONB)

    dataset: Mapped[Dataset] = relationship()


class Claim(TimestampMixin, Base):
    """A qualitative fact about a place (economic activities, languages, market days...).

    Claims are entered by researchers with a stated source. They are never generated.
    """

    __tablename__ = "claim"
    __table_args__ = (Index("ix_claim_subject", "subject_type", "subject_id", "attribute"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subject_type: Mapped[str] = mapped_column(str_enum(*CLAIM_SUBJECTS, name="claim_subject"))
    subject_id: Mapped[int] = mapped_column(Integer, nullable=False)
    attribute: Mapped[str] = mapped_column(String(64), nullable=False)
    value_text: Mapped[str] = mapped_column(Text, nullable=False)
    value_type: Mapped[str] = mapped_column(
        str_enum(*VALUE_TYPES, name="claim_value_type"), nullable=False
    )
    source_description: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1024))
    observed_on: Mapped[str | None] = mapped_column(String(32))
    verification_status: Mapped[str] = mapped_column(
        str_enum(*VERIFICATION_STATUSES, name="claim_verification"),
        default="unverified",
        server_default="unverified",
        nullable=False,
    )
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), index=True
    )
    verified_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL")
    )
    verification_note: Mapped[str | None] = mapped_column(Text)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=sa_true(), nullable=False
    )


# Attributes a claim may describe. Kept as code so the UI can offer a fixed list.
CLAIM_ATTRIBUTES = {
    "economic_activities": "Main economic activities",
    "languages": "Languages spoken",
    "market_days": "Market days",
    "community_organisations": "Community organisations",
    "infrastructure_notes": "Infrastructure observations",
    "connectivity_notes": "Connectivity observations",
    "energy_notes": "Energy access observations",
    "agriculture_notes": "Agricultural characteristics",
    "access_notes": "Physical access and security notes",
    "other": "Other",
}
