"""Accounts, roles and the audit log.

Accounts belong to people who use Connectly (staff, researchers, partner companies).
No personal data about community members is stored anywhere in the system.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy import true as sa_true
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from connectly.models.base import Base, TimestampMixin, str_enum

# admin      everything, including users, datasets and the audit log
# researcher reads everything; adds and verifies community claims; runs analyses
# company    reads everything; manages its own organisation's solutions
# viewer     read only
ROLES = ("admin", "researcher", "company", "viewer")


class User(TimestampMixin, Base):
    __tablename__ = "app_user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Stored lower-case; uniqueness is enforced on the stored value.
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(str_enum(*ROLES, name="user_role"), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=sa_true(), nullable=False
    )
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    # Incremented to revoke every token issued before (logout everywhere, password or role
    # change, deactivation).
    token_version: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    failed_logins: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # For company accounts: the organisation they may manage.
    organisation_id: Mapped[int | None] = mapped_column(
        ForeignKey("organisation.id", ondelete="SET NULL")
    )


class AuditLog(Base):
    """Append-only record of every change made through the API or CLI."""

    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_entity", "entity_type", "entity_id"),
        Index("ix_audit_log_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), index=True
    )
    # Kept so the log stays readable if the account is deleted.
    actor: Mapped[str] = mapped_column(String(320), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(64))
    summary: Mapped[str | None] = mapped_column(Text)
    # {"before": {...}, "after": {...}} for updates.
    changes: Mapped[dict | None] = mapped_column(JSONB)
    ip: Mapped[str | None] = mapped_column(String(64))
