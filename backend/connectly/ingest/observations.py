"""Store indicator values with provenance, and derive roll-ups from them.

Values only enter the database here, from a dataset row, a published table or a
documented computation. Each one names its dataset, period, value type and verification
status.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from connectly.ingest.common import LoadError, to_float
from connectly.ingest.manifest import Manifest
from connectly.models import VALUE_TYPES, VERIFICATION_STATUSES, Dataset, Indicator, Source

UPSERT_OBSERVATION = text(
    """
    INSERT INTO observation (indicator_id, geo_level, geo_id, period, value, value_text,
                             lower_bound, upper_bound, interval_note, margin_of_error,
                             value_type, verification_status, dataset_id, source_reference,
                             note)
    VALUES (:indicator_id, :geo_level, :geo_id, :period, :value, :value_text,
            :lower_bound, :upper_bound, :interval_note, :margin_of_error,
            :value_type, :verification_status, :dataset_id, :source_reference, :note)
    ON CONFLICT ON CONSTRAINT uq_observation_identity DO UPDATE
       SET value = EXCLUDED.value,
           value_text = EXCLUDED.value_text,
           lower_bound = EXCLUDED.lower_bound,
           upper_bound = EXCLUDED.upper_bound,
           interval_note = EXCLUDED.interval_note,
           margin_of_error = EXCLUDED.margin_of_error,
           value_type = EXCLUDED.value_type,
           source_reference = EXCLUDED.source_reference,
           note = EXCLUDED.note,
           updated_at = now()
    """
)


@dataclass
class StoreResult:
    stored: int = 0
    missing: int = 0
    warnings: list[str] = field(default_factory=list)


def indicator_id(session: Session, code: str) -> int:
    ind = session.scalar(select(Indicator.id).where(Indicator.code == code))
    if ind is None:
        raise LoadError(f"indicator {code!r} is not defined; run `connectly seed` first")
    return ind


def upsert_observation(session: Session, **values) -> None:
    if values["value_type"] not in VALUE_TYPES:
        raise LoadError(f"invalid value_type {values['value_type']!r}")
    values.setdefault("verification_status", "unverified")
    if values["verification_status"] not in VERIFICATION_STATUSES:
        raise LoadError(f"invalid verification_status {values['verification_status']!r}")
    for k in (
        "value_text",
        "lower_bound",
        "upper_bound",
        "interval_note",
        "margin_of_error",
        "source_reference",
        "note",
    ):
        values.setdefault(k, None)
    if values.get("value") is None and values.get("value_text") is None:
        raise LoadError("an observation needs a value")
    session.execute(UPSERT_OBSERVATION, values)


def store_attribute_observations(
    session: Session,
    manifest: Manifest,
    ds: Dataset,
    geo_level: str,
    attrs_by_geo_id: dict[int, dict],
) -> StoreResult:
    """Turn columns of a loaded file into observations, as declared in the manifest."""
    result = StoreResult()
    file_name = ds.file_name or manifest.key
    for spec in manifest.observations or []:
        ind_id = indicator_id(session, spec["indicator"])
        missing = 0
        for geo_id, attrs in attrs_by_geo_id.items():
            value = to_float(attrs.get(spec["value"]))
            if value is None:
                missing += 1
                continue
            lower = to_float(attrs.get(spec["lower"])) if spec.get("lower") else None
            upper = to_float(attrs.get(spec["upper"])) if spec.get("upper") else None
            if lower is not None and upper is not None and not (lower <= value <= upper):
                result.warnings.append(
                    f"{spec['indicator']} for area {geo_id}: value {value} outside its "
                    f"interval [{lower}, {upper}]"
                )
            upsert_observation(
                session,
                indicator_id=ind_id,
                geo_level=geo_level,
                geo_id=geo_id,
                period=str(spec["period"]),
                value=value,
                lower_bound=lower,
                upper_bound=upper,
                interval_note=spec.get("interval_note"),
                value_type=spec["value_type"],
                verification_status=spec.get("verification_status", "unverified"),
                dataset_id=ds.id,
                source_reference=f"{file_name}, column {spec['value']}",
                note=spec.get("note"),
            )
            result.stored += 1
        if missing:
            result.warnings.append(f"{spec['indicator']}: {missing} areas had no value")
        result.missing += missing
    return result


# --------------------------------------------------------------------------- derived


DERIVED_SOURCE_KEY = "connectly-derived"


def derived_dataset(
    session: Session, key: str, title: str, method: str, inputs: list[Dataset]
) -> Dataset:
    """A dataset record for values Connectly computed, naming every input dataset."""
    src = session.scalar(select(Source).where(Source.key == DERIVED_SOURCE_KEY))
    if src is None:
        src = Source(
            key=DERIVED_SOURCE_KEY,
            name="Connectly Intelligence (derived from listed datasets)",
            notes="Values computed by Connectly from other datasets; see each dataset's inputs.",
        )
        session.add(src)
        session.flush()
    ds = session.scalar(select(Dataset).where(Dataset.key == key))
    if ds is None:
        ds = Dataset(key=key, source_id=src.id, title=title, status="registered")
        session.add(ds)
    licences = sorted({i.licence or "unknown licence" for i in inputs})
    ds.title = title
    ds.method_summary = method
    ds.licence = "Derived from: " + "; ".join(licences)
    ds.licence_verified = all(i.licence_verified for i in inputs)
    # Commercial use only when every input explicitly allows it.
    ds.commercial_use_allowed = (
        True if inputs and all(i.commercial_use_allowed is True for i in inputs) else None
    )
    ds.limitations = "Inherits the limitations of its inputs: " + ", ".join(i.key for i in inputs)
    attributions = [a for a in ((i.extra or {}).get("attribution") for i in inputs) if a]
    ds.extra = {
        **(ds.extra or {}),
        "kind": "derived",
        "inputs": [i.key for i in inputs],
        "attribution": " ".join(dict.fromkeys(attributions)) or None,
        "licence_evidence": "Licences of the input datasets.",
    }
    session.flush()
    return ds


def aggregate_sum(
    session: Session,
    indicator_code: str,
    source_dataset: Dataset,
    from_level: str,
    to_level: str,
) -> StoreResult:
    """Sum child values into each active parent, as derived observations.

    Only point values are summed: interval bounds are not additive, so none are stored.
    A parent is skipped when any active child lacks a value, so totals are never partial.
    """
    ind_id = indicator_id(session, indicator_code)
    level_path = {("ward", "lga"): 1, ("ward", "state"): 2, ("lga", "state"): 1}
    hops = level_path.get((from_level, to_level))
    if hops is None:
        raise LoadError(f"cannot aggregate {from_level} to {to_level}")
    parent_expr = "c.parent_id" if hops == 1 else "p1.parent_id"
    join = "" if hops == 1 else "JOIN admin_area p1 ON p1.id = c.parent_id"

    rows = session.execute(
        text(
            f"""
            SELECT {parent_expr} AS parent_id,
                   count(*) AS children,
                   count(o.id) AS with_value,
                   sum(o.value) AS total,
                   min(o.period) AS period_min, max(o.period) AS period_max
            FROM admin_area c
            {join}
            LEFT JOIN observation o
              ON o.indicator_id = :ind AND o.geo_level = :from_level AND o.geo_id = c.id
             AND o.dataset_id = :src
            WHERE c.level = :from_level AND c.active AND {parent_expr} IS NOT NULL
            GROUP BY {parent_expr}
            """
        ),
        {"ind": ind_id, "from_level": from_level, "src": source_dataset.id},
    ).mappings()

    out_ds = derived_dataset(
        session,
        key=f"derived-sum-{indicator_code}-{from_level}-to-{to_level}",
        title=f"{indicator_code} summed from {from_level} to {to_level}",
        method=(
            f"Sum of {from_level}-level values of {indicator_code} from "
            f"{source_dataset.key} within each {to_level}. Interval bounds are not summed."
        ),
        inputs=[source_dataset],
    )
    result = StoreResult()
    for r in rows:
        if r["with_value"] == 0:
            continue
        if r["with_value"] < r["children"]:
            result.missing += 1
            continue
        if r["period_min"] != r["period_max"]:
            result.warnings.append(f"area {r['parent_id']}: children have mixed periods")
            continue
        upsert_observation(
            session,
            indicator_id=ind_id,
            geo_level=to_level,
            geo_id=r["parent_id"],
            period=r["period_min"],
            value=float(r["total"]),
            value_type="derived",
            dataset_id=out_ds.id,
            source_reference=(
                f"sum of {r['children']} {from_level} values from {source_dataset.key}"
            ),
        )
        result.stored += 1
    if result.missing:
        result.warnings.append(
            f"{result.missing} {to_level} areas skipped: not every {from_level} had a value"
        )
    out_ds.status = "loaded"
    out_ds.record_count = result.stored
    session.flush()
    return result
