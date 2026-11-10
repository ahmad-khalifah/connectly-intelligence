"""Directory rules shared by the API and the import command.

Input models validate every structured field against the fixed vocabularies, so the
matching engine never has to interpret free text.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from connectly.models import (
    AdminArea,
    NeedCategory,
    Organisation,
    Sector,
    Solution,
    SolutionCoverage,
    SolutionNeed,
)
from connectly.models.directory import (
    ACCESSIBILITY_FEATURES,
    BENEFICIARY_GROUPS,
    COVERAGE_KINDS,
    DELIVERY_MODELS,
    DEVICE_REQUIREMENTS,
    DISTRIBUTION_CHANNELS,
    INTERNET_REQUIREMENTS,
    LANGUAGES,
    LITERACY_REQUIREMENTS,
    ORG_TYPES,
    PARTNERSHIP_TYPES,
    POWER_REQUIREMENTS,
    PRICING_MODELS,
)

VOCABULARIES: dict[str, dict[str, str]] = {
    "org_types": ORG_TYPES,
    "delivery_models": DELIVERY_MODELS,
    "pricing_models": PRICING_MODELS,
    "internet_requirements": INTERNET_REQUIREMENTS,
    "device_requirements": DEVICE_REQUIREMENTS,
    "power_requirements": POWER_REQUIREMENTS,
    "literacy_requirements": LITERACY_REQUIREMENTS,
    "beneficiary_groups": BENEFICIARY_GROUPS,
    "distribution_channels": DISTRIBUTION_CHANNELS,
    "accessibility_features": ACCESSIBILITY_FEATURES,
    "partnership_types": PARTNERSHIP_TYPES,
    "languages": LANGUAGES,
}


class DirectoryError(ValueError):
    """A request that is well-formed but cannot be applied (unknown area, need...)."""


def _lit(d: dict) -> Any:
    return Literal[tuple(d)]  # type: ignore[valid-type]


def _url(v: str | None) -> str | None:
    if v and not v.startswith(("http://", "https://")):
        raise ValueError("must start with http:// or https://")
    return v or None


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


class OrganisationIn(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    org_type: _lit(ORG_TYPES)
    industry: str | None = Field(None, max_length=160)
    website: str | None = Field(None, max_length=512)
    description: str | None = Field(None, max_length=5000)
    headquarters: str | None = Field(None, max_length=255)
    headquarters_country: str = Field("NG", min_length=2, max_length=2)
    headquarters_state_id: int | None = None
    source_description: str = Field(
        min_length=5, max_length=2000, description="Where this information comes from"
    )
    source_url: str | None = Field(None, max_length=1024)

    _w = field_validator("website", "source_url")(_url)

    @field_validator("headquarters_country")
    @classmethod
    def upper(cls, v: str) -> str:
        if not v.isalpha():
            raise ValueError("ISO 3166-1 alpha-2 country code, e.g. NG")
        return v.upper()


class CoverageIn(BaseModel):
    area_id: int
    kind: Literal[COVERAGE_KINDS] = "operating"  # type: ignore[valid-type]


class SolutionIn(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    sector: str = Field(description="Sector code, e.g. health")
    need_codes: list[str] = Field(default_factory=list, description="e.g. health.telemedicine")
    summary: str = Field(min_length=10, max_length=400)
    description: str | None = Field(None, max_length=10000)
    delivery_model: _lit(DELIVERY_MODELS) | None = None
    target_beneficiaries: str | None = Field(None, max_length=2000)
    beneficiary_groups: list[_lit(BENEFICIARY_GROUPS)] = Field(default_factory=list)
    pricing_model: _lit(PRICING_MODELS) | None = None
    price_min_ngn: int | None = Field(None, ge=0)
    price_max_ngn: int | None = Field(None, ge=0)
    price_unit: str | None = Field(None, max_length=64)
    pricing_notes: str | None = Field(None, max_length=2000)
    nationwide: bool = False
    coverage: list[CoverageIn] = Field(default_factory=list)
    distribution_channels: list[_lit(DISTRIBUTION_CHANNELS)] = Field(default_factory=list)
    distribution_notes: str | None = Field(None, max_length=2000)
    internet_requirement: _lit(INTERNET_REQUIREMENTS) | None = None
    device_requirement: _lit(DEVICE_REQUIREMENTS) | None = None
    power_requirement: _lit(POWER_REQUIREMENTS) | None = None
    literacy_requirement: _lit(LITERACY_REQUIREMENTS) | None = None
    requirements_notes: str | None = Field(None, max_length=2000)
    languages: list[_lit(LANGUAGES)] = Field(default_factory=list)
    accessibility_features: list[_lit(ACCESSIBILITY_FEATURES)] = Field(default_factory=list)
    accessibility_notes: str | None = Field(None, max_length=2000)
    partnership_types: list[_lit(PARTNERSHIP_TYPES)] = Field(default_factory=list)
    partnership_notes: str | None = Field(None, max_length=2000)
    implementation_notes: str | None = Field(None, max_length=4000)
    evidence_of_impact: str | None = Field(None, max_length=4000)
    website: str | None = Field(None, max_length=512)
    source_description: str = Field(min_length=5, max_length=2000)
    source_url: str | None = Field(None, max_length=1024)

    _w = field_validator("website", "source_url")(_url)

    @field_validator(
        "need_codes",
        "beneficiary_groups",
        "distribution_channels",
        "languages",
        "accessibility_features",
        "partnership_types",
    )
    @classmethod
    def dedupe(cls, v: list[str]) -> list[str]:
        return _unique(v)

    @field_validator("price_max_ngn")
    @classmethod
    def range_ok(cls, v: int | None, info) -> int | None:
        lo = info.data.get("price_min_ngn")
        if v is not None and lo is not None and v < lo:
            raise ValueError("price_max_ngn must not be below price_min_ngn")
        return v


SOLUTION_SCALARS = (
    "name",
    "summary",
    "description",
    "delivery_model",
    "target_beneficiaries",
    "beneficiary_groups",
    "pricing_model",
    "price_min_ngn",
    "price_max_ngn",
    "price_unit",
    "pricing_notes",
    "nationwide",
    "distribution_channels",
    "distribution_notes",
    "internet_requirement",
    "device_requirement",
    "power_requirement",
    "literacy_requirement",
    "requirements_notes",
    "languages",
    "accessibility_features",
    "accessibility_notes",
    "partnership_types",
    "partnership_notes",
    "implementation_notes",
    "evidence_of_impact",
    "website",
    "source_description",
    "source_url",
)
AUDIT_SOLUTION_FIELDS = SOLUTION_SCALARS + (
    "sector_id",
    "status",
    "verification_status",
    "is_active",
)
ORG_FIELDS = tuple(OrganisationIn.model_fields)
AUDIT_ORG_FIELDS = ORG_FIELDS + ("status", "verification_status")


def slugify(name: str) -> str:
    ascii_ = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_.lower()).strip("-")[:120] or "organisation"


def unique_slug(session: Session, name: str, exclude_id: int | None = None) -> str:
    base = slugify(name)
    slug, n = base, 2
    while True:
        q = select(Organisation.id).where(Organisation.slug == slug)
        found = session.scalar(q)
        if found is None or found == exclude_id:
            return slug
        slug, n = f"{base}-{n}", n + 1


def apply_organisation(session: Session, org: Organisation, data: OrganisationIn) -> None:
    if data.headquarters_state_id is not None:
        area = session.get(AdminArea, data.headquarters_state_id)
        if area is None or area.level != "state":
            raise DirectoryError("headquarters_state_id must be a state")
        if data.headquarters_country != "NG":
            raise DirectoryError("headquarters_state_id is only for organisations based in Nigeria")
    for k in ORG_FIELDS:
        setattr(org, k, getattr(data, k))
    org.slug = unique_slug(session, data.name, org.id)


def apply_solution(session: Session, sol: Solution, data: SolutionIn) -> None:
    with session.no_autoflush:  # `sol` may be new and still incomplete
        _apply_solution(session, sol, data)


def _apply_solution(session: Session, sol: Solution, data: SolutionIn) -> None:
    sector = session.scalar(select(Sector).where(Sector.code == data.sector))
    if sector is None:
        raise DirectoryError(f"unknown sector {data.sector!r}")
    needs = []
    if data.need_codes:
        needs = list(
            session.scalars(select(NeedCategory).where(NeedCategory.code.in_(data.need_codes)))
        )
        missing = set(data.need_codes) - {n.code for n in needs}
        if missing:
            raise DirectoryError(f"unknown need codes: {', '.join(sorted(missing))}")
    areas = {}
    for c in data.coverage:
        a = session.get(AdminArea, c.area_id)
        if a is None or not a.active or a.level not in ("state", "lga", "ward"):
            raise DirectoryError(
                f"coverage area {c.area_id} must be an active state, LGA or ward "
                "(use nationwide for the whole country)"
            )
        areas[(c.area_id, c.kind)] = a
    for k in SOLUTION_SCALARS:
        setattr(sol, k, getattr(data, k))
    sol.sector_id = sector.id
    session.flush()
    session.execute(delete(SolutionNeed).where(SolutionNeed.solution_id == sol.id))
    session.execute(delete(SolutionCoverage).where(SolutionCoverage.solution_id == sol.id))
    session.add_all(SolutionNeed(solution_id=sol.id, need_category_id=n.id) for n in needs)
    session.add_all(
        SolutionCoverage(solution_id=sol.id, admin_area_id=aid, kind=kind) for aid, kind in areas
    )
    session.flush()


def snapshot_solution(session: Session, sol: Solution) -> dict:
    from connectly.services.audit import snapshot

    out = snapshot(sol, AUDIT_SOLUTION_FIELDS)
    out["need_codes"] = sorted(
        session.scalars(
            text(
                "SELECT n.code FROM solution_need sn JOIN need_category n "
                "ON n.id = sn.need_category_id WHERE sn.solution_id = :id"
            ),
            {"id": sol.id},
        )
    )
    out["coverage"] = sorted(
        f"{k}:{a}"
        for a, k in session.execute(
            text("SELECT admin_area_id, kind FROM solution_coverage WHERE solution_id = :id"),
            {"id": sol.id},
        )
    )
    return out


def publish(sol: Solution) -> None:
    sol.status = "published"
    sol.published_at = datetime.now(UTC)


SOLUTION_SELECT = """
    SELECT s.*, o.name AS organisation_name, o.slug AS organisation_slug,
           o.headquarters_country, o.status AS organisation_status,
           o.verification_status AS organisation_verification,
           sec.code AS sector, sec.name AS sector_name,
           coalesce((SELECT array_agg(n.code ORDER BY n.sort_order) FROM solution_need sn
                     JOIN need_category n ON n.id = sn.need_category_id
                     WHERE sn.solution_id = s.id), '{}') AS need_codes,
           coalesce((SELECT jsonb_agg(jsonb_build_object('area_id', a.id, 'name', a.name,
                         'level', a.level, 'kind', c.kind) ORDER BY a.level, a.name)
                     FROM solution_coverage c JOIN admin_area a ON a.id = c.admin_area_id
                     WHERE c.solution_id = s.id), '[]') AS coverage,
           cu.full_name AS created_by
    FROM solution s
    JOIN organisation o ON o.id = s.organisation_id
    JOIN sector sec ON sec.id = s.sector_id
    LEFT JOIN app_user cu ON cu.id = s.created_by_id
"""

# A solution is available in an area if it is nationwide, or its operating coverage
# includes the area, one of its ancestors, or (partly) one of its descendants.
AVAILABILITY_SQL = """
    WITH RECURSIVE up AS (
        SELECT id, parent_id FROM admin_area WHERE id = :area
        UNION ALL SELECT a.id, a.parent_id FROM admin_area a JOIN up ON a.id = up.parent_id
    ), down AS (
        SELECT id FROM admin_area WHERE id = :area
        UNION ALL SELECT a.id FROM admin_area a JOIN down ON a.parent_id = down.id
            WHERE a.level <> 'ward' OR :include_wards
    )
    SELECT s.id,
           CASE WHEN s.nationwide THEN 'nationwide'
                WHEN EXISTS (SELECT 1 FROM solution_coverage c WHERE c.solution_id = s.id
                             AND c.kind = 'operating' AND c.admin_area_id IN (SELECT id FROM up))
                     THEN 'covers_area'
                WHEN EXISTS (SELECT 1 FROM solution_coverage c WHERE c.solution_id = s.id
                             AND c.kind = 'operating' AND c.admin_area_id IN (SELECT id FROM down))
                     THEN 'covers_part'
                WHEN EXISTS (SELECT 1 FROM solution_coverage c WHERE c.solution_id = s.id
                             AND c.kind = 'expansion_interest'
                             AND (c.admin_area_id IN (SELECT id FROM up)
                                  OR c.admin_area_id IN (SELECT id FROM down)))
                     THEN 'expansion_interest'
                WHEN NOT EXISTS (SELECT 1 FROM solution_coverage c WHERE c.solution_id = s.id)
                     THEN 'unknown'
                ELSE 'not_available' END AS availability
    FROM solution s WHERE s.id = ANY(:ids)
"""


def availability(session: Session, area_id: int, solution_ids: list[int]) -> dict[int, str]:
    if not solution_ids:
        return {}
    level = session.scalar(text("SELECT level FROM admin_area WHERE id = :id"), {"id": area_id})
    rows = session.execute(
        text(AVAILABILITY_SQL),
        {"area": area_id, "ids": solution_ids, "include_wards": level in ("lga", "ward")},
    )
    return dict(rows.all())
