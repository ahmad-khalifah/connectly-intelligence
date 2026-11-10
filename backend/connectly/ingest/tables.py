"""Import area-level indicator values from published statistics.

indicator_table: a CSV transcribed from a published report (e.g. EFInA A2F state tables,
NCC state subscriptions). Every row must carry a reference (page, table) back to the
publication, and is checked: known area, allowed indicator, numeric value, sane range.

dhs_api: the DHS Program indicator API (https://api.dhsprogram.com). The raw JSON response
is saved next to the other downloads and loaded from there, so a load is repeatable and the
exact response is kept. Each requested indicator's returned label is checked against the
expected wording, so a wrong indicator id fails loudly instead of loading the wrong measure.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pandas as pd
from sqlalchemy import text
from sqlalchemy.orm import Session

from connectly.core.config import get_settings
from connectly.ingest.common import (
    LoadError,
    LoadReport,
    clean_name,
    finish_run,
    manifest_fingerprint,
    resolve_file,
    skip_if_loaded,
    start_run,
    to_float,
    upsert_dataset,
)
from connectly.ingest.fetch import FetchError, RetrievedFile, describe_local_file, sha256_of
from connectly.ingest.manifest import Manifest
from connectly.ingest.observations import indicator_id, upsert_observation
from connectly.models import VALUE_TYPES


def _area_lookup(session: Session, level: str) -> dict[str, int]:
    """Lower-cased names and aliases of active areas → id. Ambiguous keys are dropped."""
    rows = session.execute(
        text(
            """
            SELECT a.id, lower(a.name) AS k FROM admin_area a WHERE a.level = :l AND a.active
            UNION ALL
            SELECT a.id, lower(p.alias) FROM place_alias p
            JOIN admin_area a ON a.id = p.admin_area_id WHERE a.level = :l AND a.active
            """
        ),
        {"l": level},
    ).all()
    seen: dict[str, set[int]] = {}
    for area_id, key in rows:
        seen.setdefault(key, set()).add(area_id)
    return {k: next(iter(v)) for k, v in seen.items() if len(v) == 1}


def _unit(session: Session, code: str) -> str:
    return session.scalar(text("SELECT unit FROM indicator WHERE code = :c"), {"c": code}) or ""


def _check_range(unit: str, value: float) -> str | None:
    if "%" in unit and not (0 <= value <= 100):
        return f"percentage {value} outside 0–100"
    if value < 0 and "change" not in unit:
        return f"negative value {value}"
    return None


# --------------------------------------------------------------------------- CSV tables


def load_indicator_table(
    session: Session,
    manifest: Manifest,
    file: Path | None = None,
    force: bool = False,
    raw_dir: Path | None = None,
) -> LoadReport:
    cfg = manifest.table or {}
    level = cfg.get("geo_level", "state")
    cols = {
        "area": "area",
        "indicator": "indicator_code",
        "period": "period",
        "value": "value",
        "lower": "lower",
        "upper": "upper",
        "value_type": "value_type",
        "reference": "source_reference",
    } | (cfg.get("columns") or {})
    allowed = set(cfg.get("allowed_indicators") or [])
    path = resolve_file(manifest, file, raw_dir)
    retrieved = describe_local_file(path)
    params = {"file": path.name, "manifest": manifest_fingerprint(manifest)}
    ds = upsert_dataset(session, manifest, retrieved)
    skipped = skip_if_loaded(session, ds, retrieved.sha256, params, force)
    if skipped:
        return LoadReport(manifest.key, "skipped", run_id=skipped.id, warnings=skipped.warnings)
    run = start_run(session, ds, params)
    report = LoadReport(manifest.key, "running")

    df = pd.read_csv(path, dtype=str, keep_default_na=False, comment="#")
    report.rows_read = len(df)
    missing_cols = [
        c
        for k, c in cols.items()
        if k in ("area", "indicator", "period", "value", "reference") and c not in df.columns
    ]
    if missing_cols:
        raise LoadError(f"{path.name} lacks columns {missing_cols}; has {list(df.columns)}")
    if df.empty:
        raise LoadError(
            f"{path.name} has no data rows. Fill it in from the publication "
            f"({manifest.landing_url}) with a page or table reference on every row."
        )
    areas = _area_lookup(session, level)
    problems: list[str] = []
    valid: list[dict] = []
    # Validate every row first; nothing is written unless the whole file is valid.
    for i, row in df.iterrows():
        line = i + 2
        area_name = clean_name(row[cols["area"]])
        code = clean_name(row[cols["indicator"]])
        value = to_float(row[cols["value"]])
        ref = clean_name(row[cols["reference"]])
        vtype = clean_name(row.get(cols["value_type"])) or cfg.get("value_type", "measured")
        area_id = areas.get((area_name or "").lower())
        if area_id is None:
            problems.append(f"line {line}: unknown or ambiguous {level} {area_name!r}")
            continue
        if allowed and code not in allowed:
            problems.append(f"line {line}: indicator {code!r} not allowed for this dataset")
            continue
        if value is None:
            problems.append(f"line {line}: value is not a number")
            continue
        if not ref:
            problems.append(f"line {line}: no source reference (page or table)")
            continue
        if vtype not in VALUE_TYPES or vtype == "ai_generated":
            problems.append(f"line {line}: invalid value_type {vtype!r}")
            continue
        try:
            ind = indicator_id(session, code)
        except LoadError as e:
            problems.append(f"line {line}: {e}")
            continue
        bad = _check_range(_unit(session, code), value)
        if bad:
            problems.append(f"line {line}: {bad}")
            continue
        valid.append(
            {
                "indicator_id": ind,
                "geo_level": level,
                "geo_id": area_id,
                "period": str(row[cols["period"]]).strip(),
                "value": value,
                "lower_bound": to_float(row.get(cols["lower"])),
                "upper_bound": to_float(row.get(cols["upper"])),
                "value_type": vtype,
                "dataset_id": ds.id,
                "source_reference": ref,
            }
        )
    if problems:
        raise LoadError(f"{len(problems)} rows failed validation: " + "; ".join(problems[:15]))
    for values in valid:
        upsert_observation(session, **values)
    stored = len(valid)
    report.rows_loaded = stored
    finish_run(session, run, ds, report, retrieved.sha256, params, stored)
    return report


# --------------------------------------------------------------------------- DHS API


DHS_LABEL_PREFIX = re.compile(r"^[.\s]+")


def dhs_response_path(manifest: Manifest, raw_dir: Path | None = None) -> Path:
    return (raw_dir or get_settings().raw_dir) / manifest.key / "dhs_response.json"


def fetch_dhs(manifest: Manifest, raw_dir: Path | None = None) -> RetrievedFile:
    cfg = manifest.api or {}
    ids = [i["dhs_id"] for i in cfg["indicators"]]
    params = {
        "countryIds": cfg.get("country", "NG"),
        "surveyIds": cfg["survey_id"],
        "indicatorIds": ",".join(ids),
        "breakdown": cfg.get("breakdown", "subnational"),
        "f": "json",
        "perpage": 5000,
    }
    dest = dhs_response_path(manifest, raw_dir)
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        r = httpx.get(cfg["base_url"], params=params, timeout=get_settings().download_timeout)
    except httpx.HTTPError as e:
        raise FetchError(f"DHS API request failed: {e}") from e
    if r.status_code != 200:
        raise FetchError(f"DHS API returned HTTP {r.status_code}: {r.text[:300]}")
    payload = r.json()
    payload["_connectly_request"] = {
        "url": str(r.url),
        "retrieved_at": datetime.now(UTC).isoformat(),
    }
    dest.write_text(json.dumps(payload, indent=1))
    return RetrievedFile(
        dest, sha256_of(dest), dest.stat().st_size, str(r.url), datetime.now(UTC), sha256_of(dest)
    )


def _state_from_label(label: str, areas: dict[str, int]) -> int | None:
    """DHS labels look like '..Adamawa' or 'North East : Adamawa'. Zones return None."""
    clean = DHS_LABEL_PREFIX.sub("", label or "").strip()
    if " : " in clean:
        clean = clean.split(" : ")[-1]
    return areas.get(clean.lower())


def load_dhs(
    session: Session,
    manifest: Manifest,
    file: Path | None = None,
    force: bool = False,
    raw_dir: Path | None = None,
) -> LoadReport:
    cfg = manifest.api or {}
    path = file or dhs_response_path(manifest, raw_dir)
    if not Path(path).exists():
        resolve_file(manifest, None, raw_dir)  # raises a clear "fetch first" message
    retrieved = describe_local_file(Path(path), url=cfg.get("base_url"))
    params = {"file": Path(path).name, "manifest": manifest_fingerprint(manifest)}
    ds = upsert_dataset(session, manifest, retrieved)
    skipped = skip_if_loaded(session, ds, retrieved.sha256, params, force)
    if skipped:
        return LoadReport(manifest.key, "skipped", run_id=skipped.id, warnings=skipped.warnings)
    run = start_run(session, ds, params)
    report = LoadReport(manifest.key, "running")

    payload = json.loads(Path(path).read_text())
    data = payload.get("Data") or []
    report.rows_read = len(data)
    if not data:
        raise LoadError("the DHS response contains no data rows")
    areas = _area_lookup(session, "state")
    by_id = {i["dhs_id"]: i for i in cfg["indicators"]}
    seen_labels: dict[str, str] = {}
    stored = 0
    skipped_rows = 0
    for row in data:
        spec = by_id.get(row.get("IndicatorId"))
        if spec is None:
            continue
        label = row.get("Indicator") or ""
        seen_labels[row["IndicatorId"]] = label
        if spec["expect_label_contains"].lower() not in label.lower():
            raise LoadError(
                f"DHS indicator {row['IndicatorId']} is {label!r}, which does not contain "
                f"{spec['expect_label_contains']!r}. Fix the indicator id in the manifest."
            )
        # Totals only (no background breakdown such as wealth quintile).
        if row.get("ByVariableLabel") not in (None, ""):
            continue
        state_id = _state_from_label(row.get("CharacteristicLabel", ""), areas)
        value = to_float(row.get("Value"))
        if state_id is None or value is None:
            skipped_rows += 1
            continue
        upsert_observation(
            session,
            indicator_id=indicator_id(session, spec["indicator"]),
            geo_level="state",
            geo_id=state_id,
            period=str(row.get("SurveyYearLabel") or row.get("SurveyYear")),
            value=value,
            lower_bound=to_float(row.get("CILow")),
            upper_bound=to_float(row.get("CIHigh")),
            interval_note="95% confidence interval as published by the DHS Program"
            if row.get("CILow") not in (None, "")
            else None,
            value_type="measured",
            dataset_id=ds.id,
            source_reference=(
                f"DHS API {row.get('SurveyId')} indicator {row['IndicatorId']}, "
                f"{row.get('CharacteristicLabel')}"
            ),
        )
        stored += 1
    missing = set(by_id) - set(seen_labels)
    if missing:
        report.warnings.append(f"indicators not in the response: {sorted(missing)}")
    if skipped_rows:
        report.warnings.append(f"skipped {skipped_rows} rows that are zones or have no value")
    if not stored:
        raise LoadError("no state-level values matched; check survey id and breakdown")
    report.rows_loaded = stored
    finish_run(session, run, ds, report, retrieved.sha256, params, stored)
    return report
