"""Where data comes from: sources, dataset releases and ingestion runs."""

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from connectly.models.base import Base, TimestampMixin, str_enum


class Source(TimestampMixin, Base):
    """An organisation or programme that publishes data (e.g. GRID3, NBS, EFInA)."""

    __tablename__ = "source"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str | None] = mapped_column(String(1024))
    notes: Mapped[str | None] = mapped_column(Text)

    datasets: Mapped[list["Dataset"]] = relationship(back_populates="source")


class Dataset(TimestampMixin, Base):
    """One release of one dataset from one source, with its licence and limitations."""

    __tablename__ = "dataset"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    source_id: Mapped[int] = mapped_column(ForeignKey("source.id"), nullable=False)
    # Who distributes the file we actually downloaded, when it differs from the
    # original producer (e.g. geoBoundaries redistributing GRID3 boundaries).
    distributor: Mapped[str | None] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    version: Mapped[str | None] = mapped_column(String(128))
    publication_date: Mapped[date | None] = mapped_column(Date)
    # Free text when the publisher gives no clean date (e.g. "Sun Feb 26 12:26:14 2023").
    source_update_text: Mapped[str | None] = mapped_column(String(255))
    reference_period: Mapped[str | None] = mapped_column(String(128))
    geographic_coverage: Mapped[str | None] = mapped_column(String(512))
    method_summary: Mapped[str | None] = mapped_column(Text)
    limitations: Mapped[str | None] = mapped_column(Text)
    licence: Mapped[str | None] = mapped_column(String(255))
    licence_url: Mapped[str | None] = mapped_column(String(1024))
    # False until someone has read the licence on the publisher's own page.
    licence_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # None means "not yet determined"; only True datasets may feed commercial outputs.
    commercial_use_allowed: Mapped[bool | None] = mapped_column(Boolean)
    landing_url: Mapped[str | None] = mapped_column(String(1024))
    download_url: Mapped[str | None] = mapped_column(String(1024))
    file_name: Mapped[str | None] = mapped_column(String(512))
    file_sha256: Mapped[str | None] = mapped_column(String(64))
    file_bytes: Mapped[int | None] = mapped_column(BigInteger)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    record_count: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(
        str_enum("registered", "loaded", "failed", "superseded", name="dataset_status"),
        default="registered",
        nullable=False,
    )
    extra: Mapped[dict | None] = mapped_column(JSONB)

    source: Mapped[Source] = relationship(back_populates="datasets")
    runs: Mapped[list["IngestRun"]] = relationship(back_populates="dataset")


class IngestRun(Base):
    """An audit record of one attempt to load a dataset."""

    __tablename__ = "ingest_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("dataset.id", ondelete="CASCADE"))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(
        str_enum("running", "succeeded", "failed", "skipped", name="ingest_run_status"),
        default="running",
        nullable=False,
    )
    rows_read: Mapped[int | None] = mapped_column(Integer)
    rows_loaded: Mapped[int | None] = mapped_column(Integer)
    rows_rejected: Mapped[int | None] = mapped_column(Integer)
    warnings: Mapped[list | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(Text)
    parameters: Mapped[dict | None] = mapped_column(JSONB)

    dataset: Mapped[Dataset] = relationship(back_populates="runs")
