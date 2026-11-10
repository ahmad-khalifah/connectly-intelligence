"""Response models. Field names are the public API contract."""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel


class DatasetRef(BaseModel):
    key: str
    title: str
    version: str | None
    source_name: str
    distributor: str | None
    licence: str | None
    licence_verified: bool
    attribution: str | None


class Dataset(DatasetRef):
    id: int
    status: str
    publication_date: date | None
    source_update_text: str | None
    reference_period: str | None
    geographic_coverage: str | None
    method_summary: str | None
    limitations: str | None
    licence_url: str | None
    licence_evidence: str | None
    commercial_use_allowed: bool | None
    landing_url: str | None
    download_url: str | None
    file_name: str | None
    file_sha256: str | None
    retrieved_at: datetime | None
    record_count: int | None
    level: str | None


class AreaSummary(BaseModel):
    id: int
    level: str
    name: str
    parent_id: int | None
    area_km2: float | None
    child_count: int


class AreaRef(BaseModel):
    id: int
    level: str
    name: str


class Notice(BaseModel):
    """Something the user must know about missing or limited data for this area."""

    code: str
    title: str
    description: str


class AreaDetail(BaseModel):
    id: int
    level: str
    name: str
    source_name: str
    source_code: str
    area_km2: float | None
    centroid: tuple[float, float] | None  # (lon, lat)
    bbox: tuple[float, float, float, float] | None
    breadcrumbs: list[AreaRef]
    child_level: str | None
    child_count: int
    aliases: list[str]
    parent_method: str | None
    parent_overlap: float | None
    dataset: DatasetRef
    notices: list[Notice]


class NeedCategory(BaseModel):
    code: str
    name: str


class Sector(BaseModel):
    code: str
    name: str
    description: str | None
    is_priority: bool
    needs: list[NeedCategory]
    indicator_count: int
    observation_count: int


class DataGap(BaseModel):
    code: str
    sector: str | None
    title: str
    description: str
    geographic_scope: str
    status: str
    candidate_sources: str | None
    needs_field_verification: bool
    identified_on: date | None


class Stats(BaseModel):
    """Counts read directly from the database. Nothing here is estimated."""

    areas_by_level: dict[str, int]
    settlements: int
    settlements_verified: int
    facilities_by_kind: dict[str, int]
    claims: int
    datasets_loaded: int
    datasets_registered: int
    sectors: int
    indicators_defined: int
    observations: int
    open_data_gaps: int
    claims_verified: int = 0
    organisations_active: int = 0
    solutions_published: int = 0
    solutions_awaiting_review: int = 0
    reports: int = 0
    observations_by_sector: dict[str, int] = {}
    focus_state: dict | None = None
    generated_at: datetime


class FeatureCollection(BaseModel):
    type: str = "FeatureCollection"
    features: list[dict[str, Any]]
    simplified_tolerance_deg: float
    attribution: list[str]
