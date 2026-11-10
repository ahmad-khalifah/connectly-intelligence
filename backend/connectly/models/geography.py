"""The administrative hierarchy: country → state → LGA → ward.

Each row belongs to the dataset it was loaded from. Several releases of the same level
can coexist; exactly one dataset per level is `active` and is what the API serves.
Parents are assigned spatially (largest overlap) so the hierarchy is checked against
geometry rather than trusted from name fields.
"""

from geoalchemy2 import Geometry
from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from connectly.models.base import ADMIN_LEVELS, Base, TimestampMixin, str_enum
from connectly.models.provenance import Dataset


class AdminArea(TimestampMixin, Base):
    __tablename__ = "admin_area"
    __table_args__ = (
        UniqueConstraint("dataset_id", "level", "source_code", name="uq_admin_area_dataset_code"),
        Index("ix_admin_area_level_active", "level", "active"),
        Index("ix_admin_area_name", "name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    level: Mapped[str] = mapped_column(str_enum(*ADMIN_LEVELS, name="admin_level"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # The name exactly as it appears in the source file, before cleaning.
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # The identifier used by the source (GRID3 code, geoBoundaries shapeID, P-code...).
    source_code: Mapped[str] = mapped_column(String(128), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("admin_area.id", ondelete="SET NULL"), index=True
    )
    # How the parent was found and how much of this area lies inside it (0–1).
    parent_method: Mapped[str | None] = mapped_column(
        str_enum("spatial_overlap", "none", name="parent_method")
    )
    parent_overlap: Mapped[float | None] = mapped_column(Float)
    dataset_id: Mapped[int] = mapped_column(
        ForeignKey("dataset.id", ondelete="CASCADE"), nullable=False, index=True
    )
    active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    area_km2: Mapped[float | None] = mapped_column(Float)
    geom = mapped_column(Geometry("MULTIPOLYGON", srid=4326, spatial_index=True), nullable=False)
    # Any other attributes from the source row, kept verbatim.
    attributes: Mapped[dict | None] = mapped_column(JSONB)

    parent: Mapped["AdminArea | None"] = relationship(remote_side="AdminArea.id")
    dataset: Mapped[Dataset] = relationship()


class PlaceAlias(Base):
    """Alternative spellings, so names from other datasets can be matched."""

    __tablename__ = "place_alias"
    __table_args__ = (UniqueConstraint("admin_area_id", "alias", name="uq_place_alias_area_alias"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admin_area_id: Mapped[int] = mapped_column(
        ForeignKey("admin_area.id", ondelete="CASCADE"), nullable=False, index=True
    )
    alias: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str | None] = mapped_column(String(255))
    extra: Mapped[dict | None] = mapped_column(JSONB)
