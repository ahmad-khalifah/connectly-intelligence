"""Idempotent upsert of sectors, need categories, indicator definitions and data gaps."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from connectly.models import DataGap, Indicator, NeedCategory, Sector
from connectly.taxonomy.seed_data import DATA_GAPS, IDENTIFIED, INDICATORS, SECTORS


@dataclass
class SeedResult:
    sectors: int
    needs: int
    indicators: int
    gaps: int


def _get_or_new(session: Session, model, **key):
    obj = session.scalar(select(model).filter_by(**key))
    if obj is None:
        obj = model(**key)
        session.add(obj)
    return obj


def seed_reference_data(session: Session) -> SeedResult:
    sectors: dict[str, Sector] = {}
    need_count = 0
    for order, spec in enumerate(SECTORS):
        sector = _get_or_new(session, Sector, code=spec["code"])
        sector.name = spec["name"]
        sector.description = spec["description"]
        sector.is_priority = spec["priority"]
        sector.sort_order = order
        session.flush()
        sectors[spec["code"]] = sector
        for n_order, (code, name) in enumerate(spec["needs"]):
            need = _get_or_new(session, NeedCategory, code=f"{spec['code']}.{code}")
            need.sector_id = sector.id
            need.name = name
            need.sort_order = n_order
            need_count += 1

    for spec in INDICATORS:
        ind = _get_or_new(session, Indicator, code=spec["code"])
        ind.name = spec["name"]
        ind.sector_id = sectors[spec["sector"]].id if spec["sector"] else None
        ind.unit = spec["unit"]
        ind.higher_is_worse = spec["higher_is_worse"]
        ind.description = spec["description"]
        ind.method = spec["method"]

    for spec in DATA_GAPS:
        gap = _get_or_new(session, DataGap, code=spec["code"])
        gap.sector_id = sectors[spec["sector"]].id if spec["sector"] else None
        gap.title = spec["title"]
        gap.description = spec["description"]
        gap.geographic_scope = spec["scope"]
        gap.candidate_sources = spec["candidates"]
        gap.needs_field_verification = spec["field"]
        if gap.identified_on is None:
            gap.identified_on = IDENTIFIED
        if gap.status is None:
            gap.status = "open"

    session.flush()
    return SeedResult(len(sectors), need_count, len(INDICATORS), len(DATA_GAPS))
