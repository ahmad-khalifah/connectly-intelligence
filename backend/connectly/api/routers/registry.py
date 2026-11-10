"""Datasets, sectors, data gaps and headline counts — all read straight from the database."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload

from connectly.api import schemas
from connectly.api.deps import get_session
from connectly.models import ADMIN_LEVELS, DataGap, Dataset, Sector

router = APIRouter(prefix="/api/v1", tags=["registry"])


def _dataset_out(d: Dataset) -> schemas.Dataset:
    extra = d.extra or {}
    return schemas.Dataset(
        id=d.id,
        key=d.key,
        title=d.title,
        version=d.version,
        source_name=d.source.name,
        distributor=d.distributor,
        licence=d.licence,
        licence_verified=d.licence_verified,
        attribution=extra.get("attribution"),
        status=d.status,
        publication_date=d.publication_date,
        source_update_text=d.source_update_text,
        reference_period=d.reference_period,
        geographic_coverage=d.geographic_coverage,
        method_summary=d.method_summary,
        limitations=d.limitations,
        licence_url=d.licence_url,
        licence_evidence=extra.get("licence_evidence"),
        commercial_use_allowed=d.commercial_use_allowed,
        landing_url=d.landing_url,
        download_url=d.download_url,
        file_name=d.file_name,
        file_sha256=d.file_sha256,
        retrieved_at=d.retrieved_at,
        record_count=d.record_count,
        level=extra.get("level"),
    )


@router.get("/datasets", response_model=list[schemas.Dataset])
def list_datasets(session: Session = Depends(get_session)):
    rows = session.scalars(
        select(Dataset).options(selectinload(Dataset.source)).order_by(Dataset.key)
    )
    return [_dataset_out(d) for d in rows]


@router.get("/datasets/{key}", response_model=schemas.Dataset)
def get_dataset(key: str, session: Session = Depends(get_session)):
    d = session.scalar(
        select(Dataset).options(selectinload(Dataset.source)).where(Dataset.key == key)
    )
    if d is None:
        raise HTTPException(404, f"no dataset {key!r}")
    return _dataset_out(d)


@router.get("/sectors", response_model=list[schemas.Sector])
def list_sectors(session: Session = Depends(get_session)):
    counts = {
        code: (ind, obs)
        for code, ind, obs in session.execute(
            text(
                """
                SELECT s.code,
                       count(DISTINCT i.id),
                       count(o.id)
                FROM sector s
                LEFT JOIN indicator i ON i.sector_id = s.id
                LEFT JOIN observation o ON o.indicator_id = i.id
                GROUP BY s.code
                """
            )
        ).all()
    }
    sectors = session.scalars(
        select(Sector).options(selectinload(Sector.needs)).order_by(Sector.sort_order)
    )
    return [
        schemas.Sector(
            code=s.code,
            name=s.name,
            description=s.description,
            is_priority=s.is_priority,
            needs=[schemas.NeedCategory(code=n.code, name=n.name) for n in s.needs],
            indicator_count=counts.get(s.code, (0, 0))[0],
            observation_count=counts.get(s.code, (0, 0))[1],
        )
        for s in sectors
    ]


@router.get("/data-gaps", response_model=list[schemas.DataGap])
def list_gaps(
    sector: str | None = None,
    status: str | None = None,
    session: Session = Depends(get_session),
):
    stmt = select(DataGap).options(selectinload(DataGap.sector)).order_by(DataGap.code)
    if sector:
        stmt = stmt.join(DataGap.sector).where(Sector.code == sector)
    if status:
        stmt = stmt.where(DataGap.status == status)
    return [
        schemas.DataGap(
            code=g.code,
            sector=g.sector.code if g.sector else None,
            title=g.title,
            description=g.description,
            geographic_scope=g.geographic_scope,
            status=g.status,
            candidate_sources=g.candidate_sources,
            needs_field_verification=g.needs_field_verification,
            identified_on=g.identified_on,
        )
        for g in session.scalars(stmt)
    ]


@router.get("/stats", response_model=schemas.Stats)
def stats(session: Session = Depends(get_session)):
    by_level = dict.fromkeys(ADMIN_LEVELS, 0) | dict(
        session.execute(
            text("SELECT level, count(*) FROM admin_area WHERE active GROUP BY level")
        ).all()
    )
    one = lambda sql: session.scalar(text(sql))  # noqa: E731
    return schemas.Stats(
        areas_by_level=by_level,
        settlements=one("SELECT count(*) FROM settlement"),
        settlements_verified=one(
            "SELECT count(*) FROM settlement "
            "WHERE verification_status IN ('source_verified', 'field_verified')"
        ),
        facilities_by_kind=dict(
            session.execute(text("SELECT kind, count(*) FROM facility GROUP BY kind")).all()
        ),
        claims=one("SELECT count(*) FROM claim WHERE is_active"),
        datasets_loaded=one("SELECT count(*) FROM dataset WHERE status = 'loaded'"),
        datasets_registered=one("SELECT count(*) FROM dataset"),
        sectors=one("SELECT count(*) FROM sector"),
        indicators_defined=one("SELECT count(*) FROM indicator"),
        observations=one("SELECT count(*) FROM observation"),
        open_data_gaps=one("SELECT count(*) FROM data_gap WHERE status <> 'resolved'"),
        generated_at=datetime.now(tz=UTC),
    )
