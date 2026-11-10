"""Saved reports: a snapshot of an analysis, reproducible from its stored parameters."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from connectly.models.base import Base, str_enum

REPORT_KINDS = ("brief", "needs", "matching", "market_entry")


class Report(Base):
    __tablename__ = "report"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(str_enum(*REPORT_KINDS, name="report_kind"), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    params: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # The analysis output exactly as it was when the report was saved.
    result: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
