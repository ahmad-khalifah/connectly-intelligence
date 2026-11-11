"""Which states a facility or settlement dataset covers, and which dataset to use per state.

Coverage decides where a dataset may produce values. A state outside a dataset's coverage
gets "no data", never zero: a file of 24 states says nothing about the other 13.

Coverage of one load is, in order of precedence:

1. ``--within-state``: that state only (intersected with the publisher's list, if any);
2. the publisher's declared list (manifest ``coverage_states``);
3. otherwise the states where the file actually has at least one record.

A national load is never assumed to cover all 37 states.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.orm import Session

from connectly.ingest.manifest import Manifest
from connectly.models import Dataset

METHOD_WITHIN = "within-state load"
METHOD_DECLARED = "declared by the publisher"
METHOD_OBSERVED = "states with at least one record in the file"

COVERAGE_TABLES = ("facility", "settlement")


class CoverageError(ValueError):
    pass


@dataclass
class Coverage:
    state_ids: list[int]
    method: str
    warnings: list[str] = field(default_factory=list)


def all_state_ids(session: Session) -> dict[int, str]:
    return dict(
        session.execute(
            text("SELECT id, name FROM admin_area WHERE level = 'state' AND active ORDER BY name")
        ).all()
    )


def resolve_state_names(session: Session, names: list[str]) -> list[int]:
    """Map state names or aliases (e.g. "FCT Abuja", "FCT") to active state ids."""
    ids, unknown = [], []
    for name in names:
        found = (
            session.execute(
                text(
                    """
                SELECT a.id FROM admin_area a
                WHERE a.level = 'state' AND a.active
                  AND (lower(a.name) = lower(:n)
                       OR EXISTS (SELECT 1 FROM place_alias p
                                  WHERE p.admin_area_id = a.id AND lower(p.alias) = lower(:n)))
                """
                ),
                {"n": name.strip()},
            )
            .scalars()
            .all()
        )
        if len(found) == 1:
            ids.append(found[0])
        else:
            unknown.append(name)
    if unknown:
        raise CoverageError(
            f"coverage_states lists names that match no single loaded state: {unknown}. "
            "Use the state names shown by `connectly ingest list`, or add an alias."
        )
    return sorted(set(ids))


def observed_state_ids(session: Session, table: str, dataset_id: int) -> list[int]:
    if table not in COVERAGE_TABLES:
        raise ValueError(table)
    return list(
        session.execute(
            text(
                f"SELECT DISTINCT state_id FROM {table} "
                "WHERE dataset_id = :ds AND state_id IS NOT NULL ORDER BY state_id"
            ),
            {"ds": dataset_id},
        ).scalars()
    )


def compute_coverage(
    session: Session, manifest: Manifest, ds: Dataset, table: str, within_sid: int | None
) -> Coverage:
    """Decide and record coverage. Call after records are linked to states."""
    states = all_state_ids(session)
    observed = set(observed_state_ids(session, table, ds.id))
    warnings: list[str] = []

    declared = (
        set(resolve_state_names(session, manifest.coverage_states))
        if (manifest.coverage_states)
        else None
    )

    if within_sid is not None:
        covered = {within_sid} & declared if declared is not None else {within_sid}
        method = METHOD_WITHIN
        if declared is not None and not covered:
            warnings.append(
                f"{states[within_sid]} is not in the publisher's declared coverage; "
                "no state is treated as covered"
            )
    elif declared is not None:
        covered, method = declared, METHOD_DECLARED
        outside = observed - declared
        if outside:
            warnings.append(
                f"records found in {len(outside)} states outside the declared coverage "
                f"({', '.join(states[s] for s in sorted(outside))}); they are kept but not "
                "used for derived values there"
            )
    else:
        covered, method = observed, METHOD_OBSERVED

    empty = sorted(covered - observed)
    if empty:
        warnings.append(
            f"covered states with no records: {', '.join(states[s] for s in empty)}. "
            "Check the file; derived values there will show zero."
        )
    missing = sorted(set(states) - covered)
    if missing and within_sid is None:
        warnings.append(
            f"covers {len(covered)} of {len(states)} states; not covered: "
            + ", ".join(states[s] for s in missing)
        )

    ds.extra = {
        **(ds.extra or {}),
        "coverage_state_ids": sorted(covered),
        "coverage_method": method,
    }
    return Coverage(sorted(covered), method, warnings)


def dataset_state_ids(session: Session, ds: Dataset, table: str) -> list[int]:
    """Coverage of a dataset; older records without it fall back to observed states."""
    ids = (ds.extra or {}).get("coverage_state_ids")
    if ids is not None:
        return list(ids)
    return observed_state_ids(session, table, ds.id)


def _preference(ds: Dataset) -> tuple:
    extra = ds.extra or {}
    pub = ds.publication_date.toordinal() if ds.publication_date else 0
    got = ds.retrieved_at.timestamp() if ds.retrieved_at else 0
    return (int(extra.get("priority", 100)), -pub, -got, -ds.id)


def sources_by_state(session: Session, datasets: list[Dataset], table: str) -> dict[int, Dataset]:
    """For each covered state, the single dataset to use there.

    Using one source per state avoids counting the same clinic twice when, for example,
    GRID3 and OpenStreetMap both list it, while still combining datasets that cover
    different states (GRID3 v3.0 for 24 states, v2.0 for the rest).
    """
    chosen: dict[int, Dataset] = {}
    for ds in sorted(datasets, key=_preference):
        for sid in dataset_state_ids(session, ds, table):
            chosen.setdefault(sid, ds)
    return chosen
