"""Sectors and the specific needs within them. New sectors are rows, not code."""

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from connectly.models.base import Base, TimestampMixin


class Sector(TimestampMixin, Base):
    __tablename__ = "sector"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # Sectors being implemented first (healthcare, connectivity, financial services).
    is_priority: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    needs: Mapped[list["NeedCategory"]] = relationship(
        back_populates="sector", order_by="NeedCategory.sort_order"
    )


class NeedCategory(TimestampMixin, Base):
    __tablename__ = "need_category"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sector_id: Mapped[int] = mapped_column(ForeignKey("sector.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    sector: Mapped[Sector] = relationship(back_populates="needs")
