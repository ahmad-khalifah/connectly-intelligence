"""Technology solutions directory: organisations and the solutions they offer.

There is no open register of technology solutions for Nigeria, so every record is entered
by an administrator or submitted by the organisation itself, with its source recorded.
Fields the matching engine uses are structured (fixed vocabularies below); anything not
known is left empty and treated as unknown, never guessed.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import true as sa_true
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from connectly.models.base import VERIFICATION_STATUSES, Base, TimestampMixin, str_enum

ORG_TYPES = {
    "startup": "Technology startup",
    "established": "Established technology provider",
    "telecom_operator": "Telecommunications operator",
    "financial_institution": "Bank or licensed financial institution",
    "ngo": "Non-profit or NGO",
    "social_enterprise": "Social enterprise",
    "government": "Government agency or programme",
    "cooperative": "Cooperative or association",
    "academic": "University or research institute",
    "other": "Other",
}

# Publication workflow. Only "published" solutions appear to non-admins and in matching.
SOLUTION_STATUSES = ("draft", "submitted", "published", "rejected", "retired")
ORG_STATUSES = ("submitted", "active", "rejected", "retired")

DELIVERY_MODELS = {
    "mobile_app": "Mobile app",
    "web_platform": "Web platform",
    "ussd_sms": "USSD or SMS service",
    "agent_network": "Agent or field network",
    "hardware": "Hardware or equipment",
    "infrastructure": "Infrastructure",
    "service": "Service delivered by staff",
    "programme": "Programme or training",
}

PRICING_MODELS = {
    "free": "Free to the user",
    "freemium": "Free with paid features",
    "subscription": "Subscription",
    "pay_per_use": "Pay per use or transaction",
    "one_off": "One-off purchase",
    "pay_as_you_go": "Pay-as-you-go instalments",
    "b2b_contract": "Contract with an institution",
    "donor_funded": "Funded by a donor or government",
}

# What the end user needs in order to use the solution.
INTERNET_REQUIREMENTS = {
    "none": "No internet needed",
    "sms_ussd": "Mobile network only (SMS or USSD)",
    "intermittent": "Works offline, syncs when connected",
    "mobile_2g": "2G data",
    "mobile_3g": "3G data or better",
    "broadband_4g": "4G or fixed broadband",
}
INTERNET_RANK = {k: i for i, k in enumerate(INTERNET_REQUIREMENTS)}

DEVICE_REQUIREMENTS = {
    "none": "No device needed by the user",
    "basic_phone": "Any mobile phone",
    "smartphone": "Smartphone",
    "computer": "Computer",
    "special_hardware": "Equipment supplied with the solution",
}
DEVICE_RANK = {"none": 0, "basic_phone": 1, "special_hardware": 1, "smartphone": 2, "computer": 3}

POWER_REQUIREMENTS = {
    "none": "No electricity needed",
    "self_powered": "Includes its own power (solar, battery)",
    "occasional_charging": "Occasional phone charging",
    "grid": "Reliable mains electricity",
}

LITERACY_REQUIREMENTS = {
    "none": "None (voice, pictures or assisted)",
    "basic": "Basic reading",
    "functional": "Comfortable reading and writing",
    "digital": "Digital skills",
}

BENEFICIARY_GROUPS = {
    "households": "Households",
    "women": "Women",
    "youth": "Young people",
    "children": "Children",
    "older_people": "Older people",
    "people_with_disabilities": "People with disabilities",
    "smallholder_farmers": "Smallholder farmers",
    "pastoralists": "Pastoralists",
    "traders": "Traders and market sellers",
    "msmes": "Micro, small and medium enterprises",
    "transport_operators": "Transport operators",
    "students": "Students",
    "teachers": "Teachers",
    "schools": "Schools",
    "patients": "Patients",
    "health_workers": "Health workers",
    "health_facilities": "Health facilities",
    "displaced_people": "Displaced people",
    "local_government": "Local government",
}

DISTRIBUTION_CHANNELS = {
    "direct_digital": "Direct download or sign-up",
    "agents": "Agents or field representatives",
    "retail": "Shops and retail outlets",
    "mobile_operator": "Mobile network operator",
    "bank_partner": "Bank or financial institution",
    "ngo_partner": "NGO or development partner",
    "government": "Government programme",
    "health_facilities": "Health facilities",
    "schools": "Schools",
    "cooperatives": "Cooperatives and associations",
    "community_leaders": "Community and religious leaders",
}

ACCESSIBILITY_FEATURES = {
    "voice": "Voice or audio interface",
    "local_language_audio": "Audio in local languages",
    "low_literacy_design": "Designed for low literacy",
    "assisted_use": "Used with help from an agent or worker",
    "offline_mode": "Works offline",
    "screen_reader": "Screen reader support",
    "large_text": "Large text or high contrast",
}

PARTNERSHIP_TYPES = {
    "distribution": "Distribution partners",
    "ngo": "NGOs and development partners",
    "government": "Government",
    "financing": "Financing and investment",
    "research": "Research and evaluation",
    "local_operator": "Local operating partners",
}

# ISO 639 codes for languages widely spoken in Nigeria.
LANGUAGES = {
    "en": "English",
    "pcm": "Nigerian Pidgin",
    "ha": "Hausa",
    "yo": "Yoruba",
    "ig": "Igbo",
    "ff": "Fulfulde",
    "kr": "Kanuri",
    "tiv": "Tiv",
    "ibb": "Ibibio",
    "efi": "Efik",
    "bin": "Edo",
    "ijc": "Ijaw (Izon)",
    "nup": "Nupe",
    "igl": "Igala",
    "idu": "Idoma",
    "bwr": "Bura-Pabir",
    "mfi": "Wandala",
    "bci": "Bachama",
    "hig": "Kamwe",
    "ar": "Arabic",
    "fr": "French",
}

COVERAGE_KINDS = ("operating", "expansion_interest")


class Organisation(TimestampMixin, Base):
    __tablename__ = "organisation"
    __table_args__ = (
        CheckConstraint("char_length(headquarters_country) = 2", name="hq_country_iso2"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    org_type: Mapped[str] = mapped_column(str_enum(*ORG_TYPES, name="org_type"), nullable=False)
    industry: Mapped[str | None] = mapped_column(String(160))
    website: Mapped[str | None] = mapped_column(String(512))
    description: Mapped[str | None] = mapped_column(Text)
    headquarters: Mapped[str | None] = mapped_column(String(255))  # as stated, e.g. "Yola"
    headquarters_country: Mapped[str] = mapped_column(String(2), nullable=False)
    headquarters_state_id: Mapped[int | None] = mapped_column(
        ForeignKey("admin_area.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(
        str_enum(*ORG_STATUSES, name="org_status"), nullable=False, server_default="submitted"
    )
    verification_status: Mapped[str] = mapped_column(
        str_enum(*VERIFICATION_STATUSES, name="org_verification"),
        nullable=False,
        server_default="unverified",
    )
    verification_note: Mapped[str | None] = mapped_column(Text)
    source_description: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1024))
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL")
    )

    solutions: Mapped[list["Solution"]] = relationship(
        back_populates="organisation", order_by="Solution.name"
    )


class Solution(TimestampMixin, Base):
    __tablename__ = "solution"
    __table_args__ = (
        UniqueConstraint("organisation_id", "name", name="uq_solution_org_name"),
        Index("ix_solution_status_sector", "status", "sector_id"),
        CheckConstraint(
            "price_min_ngn IS NULL OR price_max_ngn IS NULL OR price_min_ngn <= price_max_ngn",
            name="price_range",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    organisation_id: Mapped[int] = mapped_column(
        ForeignKey("organisation.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sector_id: Mapped[int] = mapped_column(ForeignKey("sector.id"), nullable=False)
    summary: Mapped[str] = mapped_column(String(400), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    delivery_model: Mapped[str | None] = mapped_column(
        str_enum(*DELIVERY_MODELS, name="delivery_model")
    )
    target_beneficiaries: Mapped[str | None] = mapped_column(Text)
    beneficiary_groups: Mapped[list[str]] = mapped_column(
        ARRAY(String(40)), nullable=False, server_default="{}"
    )

    # Pricing, as published by the provider. NULL means not known.
    pricing_model: Mapped[str | None] = mapped_column(
        str_enum(*PRICING_MODELS, name="pricing_model")
    )
    price_min_ngn: Mapped[int | None] = mapped_column(BigInteger)
    price_max_ngn: Mapped[int | None] = mapped_column(BigInteger)
    price_unit: Mapped[str | None] = mapped_column(String(64))  # "per month", "per device"
    pricing_notes: Mapped[str | None] = mapped_column(Text)

    # Coverage is in solution_coverage; nationwide means every state.
    nationwide: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    distribution_channels: Mapped[list[str]] = mapped_column(
        ARRAY(String(40)), nullable=False, server_default="{}"
    )
    distribution_notes: Mapped[str | None] = mapped_column(Text)
    internet_requirement: Mapped[str | None] = mapped_column(
        str_enum(*INTERNET_REQUIREMENTS, name="internet_requirement")
    )
    device_requirement: Mapped[str | None] = mapped_column(
        str_enum(*DEVICE_REQUIREMENTS, name="device_requirement")
    )
    power_requirement: Mapped[str | None] = mapped_column(
        str_enum(*POWER_REQUIREMENTS, name="power_requirement")
    )
    literacy_requirement: Mapped[str | None] = mapped_column(
        str_enum(*LITERACY_REQUIREMENTS, name="literacy_requirement")
    )
    requirements_notes: Mapped[str | None] = mapped_column(Text)
    languages: Mapped[list[str]] = mapped_column(
        ARRAY(String(8)), nullable=False, server_default="{}"
    )
    accessibility_features: Mapped[list[str]] = mapped_column(
        ARRAY(String(40)), nullable=False, server_default="{}"
    )
    accessibility_notes: Mapped[str | None] = mapped_column(Text)
    partnership_types: Mapped[list[str]] = mapped_column(
        ARRAY(String(40)), nullable=False, server_default="{}"
    )
    partnership_notes: Mapped[str | None] = mapped_column(Text)
    implementation_notes: Mapped[str | None] = mapped_column(Text)
    # Evidence the solution works, with where it was reported. Optional.
    evidence_of_impact: Mapped[str | None] = mapped_column(Text)
    website: Mapped[str | None] = mapped_column(String(512))

    status: Mapped[str] = mapped_column(
        str_enum(*SOLUTION_STATUSES, name="solution_status"),
        nullable=False,
        server_default="draft",
    )
    status_note: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verification_status: Mapped[str] = mapped_column(
        str_enum(*VERIFICATION_STATUSES, name="solution_verification"),
        nullable=False,
        server_default="unverified",
    )
    verification_note: Mapped[str | None] = mapped_column(Text)
    source_description: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1024))
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_true())

    organisation: Mapped[Organisation] = relationship(back_populates="solutions")


class SolutionNeed(Base):
    """Which specific needs a solution addresses (relevance in matching)."""

    __tablename__ = "solution_need"

    solution_id: Mapped[int] = mapped_column(
        ForeignKey("solution.id", ondelete="CASCADE"), primary_key=True
    )
    need_category_id: Mapped[int] = mapped_column(
        ForeignKey("need_category.id", ondelete="CASCADE"), primary_key=True
    )


class SolutionCoverage(Base):
    """Where a solution operates, or where its provider wants to expand."""

    __tablename__ = "solution_coverage"

    solution_id: Mapped[int] = mapped_column(
        ForeignKey("solution.id", ondelete="CASCADE"), primary_key=True
    )
    admin_area_id: Mapped[int] = mapped_column(
        ForeignKey("admin_area.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    kind: Mapped[str] = mapped_column(
        str_enum(*COVERAGE_KINDS, name="coverage_kind"), primary_key=True
    )
