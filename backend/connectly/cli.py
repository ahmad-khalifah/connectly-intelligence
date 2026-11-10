"""`connectly` command-line tool: database setup, reference data and ingestion."""

from __future__ import annotations

from pathlib import Path

import typer
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from connectly.core.config import BACKEND_DIR, get_settings
from connectly.core.db import get_engine, session_scope
from connectly.ingest import boundaries, fetch
from connectly.ingest.manifest import ManifestError, all_manifests, get_manifest
from connectly.taxonomy.seed import seed_reference_data

app = typer.Typer(help="Connectly Intelligence administration", no_args_is_help=True)
db_app = typer.Typer(help="Database schema", no_args_is_help=True)
ingest_app = typer.Typer(help="Dataset ingestion", no_args_is_help=True)
app.add_typer(db_app, name="db")
app.add_typer(ingest_app, name="ingest")
users_app = typer.Typer(help="User accounts", no_args_is_help=True)
app.add_typer(users_app, name="users")
directory_app = typer.Typer(help="Technology solutions directory", no_args_is_help=True)
app.add_typer(directory_app, name="directory")


def _alembic_config() -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return cfg


@db_app.command("upgrade")
def db_upgrade(revision: str = "head") -> None:
    """Apply migrations."""
    command.upgrade(_alembic_config(), revision)
    typer.echo(f"database at {revision}")


@db_app.command("check")
def db_check() -> None:
    """Confirm the database is reachable and PostGIS is installed."""
    with get_engine().connect() as conn:
        version = conn.execute(text("SELECT postgis_lib_version()")).scalar_one()
        rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    typer.echo(f"PostGIS: {version}\nmigration: {rev}")


@app.command("seed")
def seed() -> None:
    """Load sectors, need categories, indicator definitions and recorded data gaps."""
    with session_scope() as s:
        r = seed_reference_data(s)
    typer.echo(
        f"sectors: {r.sectors}, need categories: {r.needs}, "
        f"indicator definitions: {r.indicators}, data gaps: {r.gaps}"
    )


@ingest_app.command("list")
def ingest_list() -> None:
    """Show every known dataset and whether it is loaded."""
    manifests = all_manifests()
    with session_scope() as s:
        rows = {
            k: (st, n)
            for k, st, n in s.execute(text("SELECT key, status, record_count FROM dataset")).all()
        }
    for key, m in manifests.items():
        status, n = rows.get(key, ("not registered", None))
        local = fetch.default_file_for(m)
        typer.echo(
            f"{key:30} {m.level:8} {m.download.mode:6} {status:14} "
            f"{'' if n is None else n:>6}  local copy: {'yes' if local else 'no'}"
        )


@ingest_app.command("fetch")
def ingest_fetch(key: str) -> None:
    """Download a dataset that has a direct link, or query its API."""
    try:
        m = get_manifest(key)
        if m.kind == "dhs_api":
            from connectly.ingest.tables import fetch_dhs

            got = fetch_dhs(m)
        else:
            got = fetch.fetch(m)
    except (ManifestError, fetch.FetchError) as e:
        typer.secho(str(e), fg="red", err=True)
        raise typer.Exit(1) from e
    typer.echo(f"saved {got.path} ({got.bytes:,} bytes, sha256 {got.sha256[:16]}…)")


def _load(m, s, file, within_state, activate, force):
    from connectly.ingest import osm, points, tables

    if m.kind == "admin_boundaries":
        return boundaries.load_boundaries(
            s, m, file=file, within_state=within_state, activate=activate, force=force
        )
    if m.kind in ("settlements", "facilities"):
        return points.load_points(s, m, file=file, within_state=within_state, force=force)
    if m.kind == "osm_facilities":
        return osm.load_osm(s, m, file=file, within_state=within_state, force=force)
    if m.kind == "indicator_table":
        return tables.load_indicator_table(s, m, file=file, force=force)
    if m.kind == "dhs_api":
        return tables.load_dhs(s, m, file=file, force=force)
    raise boundaries.LoadError(f"no loader for kind {m.kind!r}")


@ingest_app.command("load")
def ingest_load(
    key: str,
    file: Path | None = typer.Option(None, help="Local file to load instead of the fetched copy"),
    within_state: str | None = typer.Option(
        None, help="Keep only records inside this state (needs states loaded first)"
    ),
    activate: str = typer.Option("auto", help="Boundaries only: auto | yes | no"),
    force: bool = typer.Option(False, help="Reload even if this exact file was loaded"),
) -> None:
    """Validate and load any dataset that has a manifest."""
    try:
        m = get_manifest(key)
    except ManifestError as e:
        typer.secho(str(e), fg="red", err=True)
        raise typer.Exit(1) from e
    params = {"file": str(file) if file else None, "within_state": within_state}
    try:
        with session_scope() as s:
            report = _load(m, s, file, within_state, activate, force)
    except boundaries.FileNotProvidedError as e:
        # Not a failed load: there is simply no file yet. Leave the dataset status alone.
        typer.secho(str(e), fg="yellow", err=True)
        raise typer.Exit(2) from e
    except (boundaries.LoadError, fetch.FetchError) as e:
        with session_scope() as s:
            run_id = boundaries.record_failure(s, m, str(e), params)
        typer.secho(f"FAILED (run {run_id}): {e}", fg="red", err=True)
        raise typer.Exit(1) from e

    colour = "green" if report.status == "succeeded" else "yellow"
    typer.secho(
        f"{report.status}: {key} — read {report.rows_read}, loaded {report.rows_loaded}, "
        f"rejected {report.rows_rejected}, outside scope {report.rows_out_of_scope}"
        + (f", active: {report.active}" if m.kind == "admin_boundaries" else "")
        + f" (run {report.run_id})",
        fg=colour,
    )
    for w in report.warnings:
        typer.secho(f"  note: {w}", fg="yellow")


@app.command("derive")
def derive(indicator: str | None = typer.Option(None, help="Only this indicator")) -> None:
    """Compute derived indicators from loaded facilities, settlements and population."""
    from connectly.ingest.derive import run_all

    with session_scope() as s:
        for r in run_all(s, only=indicator):
            if r.skipped_reason:
                typer.echo(f"{r.indicator:45} skipped: {r.skipped_reason}")
            else:
                typer.echo(
                    f"{r.indicator:45} " + ", ".join(f"{k} {v}" for k, v in r.stored.items())
                )


@ingest_app.command("runs")
def ingest_runs(limit: int = 15) -> None:
    """Show recent ingestion runs."""
    with session_scope() as s:
        rows = s.execute(
            text(
                """
                SELECT r.id, d.key, r.status, r.rows_read, r.rows_loaded, r.rows_rejected,
                       r.started_at, r.error
                FROM ingest_run r JOIN dataset d ON d.id = r.dataset_id
                ORDER BY r.id DESC LIMIT :n
                """
            ),
            {"n": limit},
        ).all()
    for r in rows:
        typer.echo(
            f"#{r.id:<4} {r.key:30} {r.status:10} read={r.rows_read} loaded={r.rows_loaded} "
            f"rejected={r.rows_rejected} {r.started_at:%Y-%m-%d %H:%M}"
            + (f"\n      error: {r.error[:200]}" if r.error else "")
        )


# Datasets that can be downloaded directly and are loaded by `connectly bootstrap`.
BOOTSTRAP_DATASETS = (
    "geoboundaries-nga-adm0",
    "geoboundaries-nga-adm1",
    "geoboundaries-nga-adm2",
    "geocontrast-grid3-nga-wards-2022",
)


@app.command("derive-rollups")
def derive_rollups() -> None:
    """Sum ward-level modelled population into LGAs and states (derived values)."""
    from sqlalchemy import select

    from connectly.ingest.observations import aggregate_sum
    from connectly.models import Dataset

    with session_scope() as s:
        src = s.scalar(select(Dataset).where(Dataset.key == "geocontrast-grid3-nga-wards-2022"))
        if src is None or src.status != "loaded":
            typer.secho("ward dataset not loaded; nothing to roll up", fg="yellow")
            return
        for to_level in ("lga", "state"):
            r = aggregate_sum(s, "population.modelled_total", src, "ward", to_level)
            typer.echo(f"population.modelled_total ward → {to_level}: {r.stored} values")
            for w in r.warnings:
                typer.secho(f"  warning: {w}", fg="yellow")


@app.command("bootstrap")
def bootstrap() -> None:
    """Migrate, seed, then fetch and load the national, state and LGA boundaries."""
    db_upgrade()
    seed()
    for key in BOOTSTRAP_DATASETS:
        if fetch.default_file_for(get_manifest(key)) is None:
            ingest_fetch(key)
        ingest_load(key, file=None, within_state=None, activate="auto", force=False)
    derive_rollups()
    derive(indicator=None)
    typer.echo(f"done. Raw files are in {get_settings().raw_dir}")



@users_app.command("create")
def users_create(
    email: str = typer.Option(..., help="Sign-in e-mail"),
    name: str = typer.Option(..., help="Full name"),
    role: str = typer.Option("admin", help="admin, researcher, company or viewer"),
    password: bool = typer.Option(
        False, "--password", help="Type a password now instead of issuing a temporary one"
    ),
) -> None:
    """Create an account. Use this once to create the first admin."""
    from sqlalchemy import select

    from connectly.core.security import hash_password, password_problems
    from connectly.models import ROLES, User
    from connectly.services import audit

    if role not in ROLES:
        raise typer.BadParameter(f"role must be one of {', '.join(ROLES)}")
    email = email.strip().lower()
    if "@" not in email:
        raise typer.BadParameter("not an e-mail address")
    temporary = None
    if password:
        secret = typer.prompt("Password", hide_input=True, confirmation_prompt=True)
        problems = password_problems(secret, email)
        if problems:
            typer.echo("password " + "; ".join(problems), err=True)
            raise typer.Exit(1)
    else:
        import secrets

        secret = temporary = secrets.token_urlsafe(12)
    with session_scope() as s:
        if s.scalar(select(User).where(User.email == email)):
            typer.echo(f"an account for {email} already exists", err=True)
            raise typer.Exit(1)
        user = User(
            email=email,
            full_name=name.strip(),
            role=role,
            password_hash=hash_password(secret),
            must_change_password=temporary is not None,
        )
        s.add(user)
        s.flush()
        audit.record(s, "cli", "create", "user", user.id, f"created {role} account {email}")
    typer.echo(f"created {role} account {email}")
    if temporary:
        typer.echo(f"temporary password (shown once; change it at first sign-in): {temporary}")


@users_app.command("list")
def users_list() -> None:
    """Show every account."""
    with session_scope() as s:
        rows = s.execute(
            text(
                "SELECT email, full_name, role, is_active, last_login_at FROM app_user "
                "ORDER BY role, email"
            )
        ).all()
    for email, name, role, active, last in rows:
        typer.echo(
            f"{email:36} {role:10} {'active' if active else 'disabled':8} "
            f"{name}  last sign-in: {last or 'never'}"
        )


@directory_app.command("import")
def directory_import(path: Path) -> None:
    """Create or update organisations and solutions from a YAML file (all or nothing)."""
    from connectly.services.directory import DirectoryError
    from connectly.services.directory_import import import_directory

    try:
        with session_scope() as s:
            r = import_directory(s, path)
    except DirectoryError as e:
        typer.echo(f"nothing imported: {e}", err=True)
        raise typer.Exit(1) from None
    typer.echo(
        f"organisations: {r.organisations_created} created, {r.organisations_updated} updated; "
        f"solutions: {r.solutions_created} created, {r.solutions_updated} updated"
    )


if __name__ == "__main__":
    app()
