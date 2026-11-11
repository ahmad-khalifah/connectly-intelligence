"""Research intelligence: AI usage accounting, the extraction cache, sources and findings.

What is stored, and what is deliberately not:

* Live web research answers (Gemini with Google Search grounding) are NEVER stored or
  cached, and their links are never stored. Google's terms for Grounding with Google Search
  forbid caching, storing or reusing Grounded Results and Links. Only usage counts are kept.
* A research source is a page a researcher chose and submitted by its original URL. The
  platform fetches it itself. Findings extracted from it carry a verbatim quote that was
  checked against the page, and start unverified until a person reviews them.
"""

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from connectly.models.base import VERIFICATION_STATUSES, Base, TimestampMixin, str_enum

AI_PURPOSES = ("web_research", "source_extraction", "summary")
AI_STATUSES = ("pending", "ok", "cached", "blocked_local", "rate_limited", "error")
FINDING_KINDS = ("measured", "estimated", "assumed", "opinion")


class AIUsage(Base):
    """One attempted call to a hosted model, whether or not it reached the provider."""

    __tablename__ = "ai_usage"
    __table_args__ = (Index("ix_ai_usage_day", "provider", "pacific_day"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Calendar day in US Pacific time, when Google resets daily quotas.
    pacific_day: Mapped[date] = mapped_column(Date, nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    purpose: Mapped[str] = mapped_column(str_enum(*AI_PURPOSES, name="ai_purpose"), nullable=False)
    grounded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(str_enum(*AI_STATUSES, name="ai_status"), nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    total_tokens: Mapped[int | None] = mapped_column(Integer)
    search_queries: Mapped[int | None] = mapped_column(Integer)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    # Set on a provider rate-limit reply: no further call is attempted before this time.
    blocked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("app_user.id", ondelete="SET NULL"))


class AICache(Base):
    """Cached results of non-grounded calls only (source extraction)."""

    __tablename__ = "ai_cache"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    purpose: Mapped[str] = mapped_column(str_enum(*AI_PURPOSES, name="ai_cache_purpose"))
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    response: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    hits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class ResearchSource(TimestampMixin, Base):
    """A web page or document a researcher submitted for analysis."""

    __tablename__ = "research_source"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    url: Mapped[str] = mapped_column(String(2048), unique=True, nullable=False)
    final_url: Mapped[str | None] = mapped_column(String(2048))
    title: Mapped[str | None] = mapped_column(String(512))
    publisher: Mapped[str | None] = mapped_column(String(255))
    published_on: Mapped[date | None] = mapped_column(Date)
    # How the publication date was found ("meta article:published_time", "model", ...).
    published_basis: Mapped[str | None] = mapped_column(String(128))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(128))
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False)
    submitted_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL")
    )

    findings: Mapped[list["ResearchFinding"]] = relationship(back_populates="source")


class ResearchFinding(TimestampMixin, Base):
    """One statement from a source, with the verbatim passage that supports it."""

    __tablename__ = "research_finding"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("research_source.id", ondelete="CASCADE"), nullable=False, index=True
    )
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    # What the source itself presents: a measurement, an estimate, an assumption, an opinion.
    kind: Mapped[str] = mapped_column(str_enum(*FINDING_KINDS, name="finding_kind"))
    sector_id: Mapped[int | None] = mapped_column(ForeignKey("sector.id"), index=True)
    period_text: Mapped[str | None] = mapped_column(String(128))
    # Place names as the source gives them, including any not matched to a loaded area.
    places_text: Mapped[list | None] = mapped_column(JSONB)
    # "gemini:<model>" for AI extraction (statement paraphrased by AI), or "manual".
    extracted_by: Mapped[str] = mapped_column(String(96), nullable=False)
    verification_status: Mapped[str] = mapped_column(
        str_enum(*VERIFICATION_STATUSES, name="finding_verification"),
        default="unverified",
        nullable=False,
    )
    verification_note: Mapped[str | None] = mapped_column(Text)
    verified_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL")
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL")
    )

    source: Mapped[ResearchSource] = relationship(back_populates="findings")


class ResearchFindingArea(Base):
    """Areas a finding is about, matched from the place names the source gives."""

    __tablename__ = "research_finding_area"

    finding_id: Mapped[int] = mapped_column(
        ForeignKey("research_finding.id", ondelete="CASCADE"), primary_key=True
    )
    admin_area_id: Mapped[int] = mapped_column(
        ForeignKey("admin_area.id", ondelete="CASCADE"), primary_key=True, index=True
    )
