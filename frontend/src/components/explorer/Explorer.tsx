"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Badge, ErrorBox, NoticeBox, Provenance } from "@/components/ui";
import {
  ApiError,
  type AreaDetail,
  type AreaSummary,
  type ChoroplethResponse,
  clientApi,
  type FeatureCollection,
  formatNumber,
  formatValue,
  type IndicatorInfo,
  LEVEL_LABEL,
  LEVEL_PLURAL,
  type Sector,
} from "@/lib/api";
import { classes, FACILITY_KIND_LABEL, NO_DATA, SECTOR_FACILITY_KIND } from "@/lib/sectors";

import type { Choropleth, PointLayer } from "./AreaMap";

// MapLibre touches `window`, so it only loads in the browser.
const AreaMap = dynamic(() => import("./AreaMap"), {
  ssr: false,
  loading: () => <div className="h-full min-h-[460px] w-full animate-pulse bg-paper" />,
});

interface Loaded {
  area: AreaDetail;
  children: AreaSummary[];
  outline: FeatureCollection;
  childShapes: FeatureCollection | null;
}

async function loadArea(id: number): Promise<Loaded> {
  const area = await clientApi<AreaDetail>(`/api/v1/areas/${id}`);
  const [children, outline, childShapes] = await Promise.all([
    clientApi<AreaSummary[]>(`/api/v1/areas/${id}/children`),
    clientApi<FeatureCollection>(`/api/v1/areas/${id}/geojson`),
    area.child_level && area.child_count > 0
      ? clientApi<FeatureCollection>(`/api/v1/geojson?level=${area.child_level}&parent_id=${id}`)
      : Promise.resolve(null),
  ]);
  return { area, children, outline, childShapes };
}

interface PointsResponse extends GeoJSON.FeatureCollection {
  attribution: string[];
}

export default function Explorer() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const requested = Number(params.get("area")) || null;
  const sector = params.get("sector") ?? "";
  const indicatorParam = params.get("indicator");
  const showFacilities = params.get("facilities") === "1";
  const showSettlements = params.get("settlements") === "1";

  const [rootId, setRootId] = useState<number | null>(null);
  const [rootError, setRootError] = useState<string | null>(null);
  const [result, setResult] = useState<{ id: number; data: Loaded } | { id: number; error: string } | null>(null);
  const [filter, setFilter] = useState("");
  const [catalogue, setCatalogue] = useState<IndicatorInfo[]>([]);
  const [sectors, setSectors] = useState<Sector[]>([]);
  const [choro, setChoro] = useState<{ key: string; data: ChoroplethResponse } | null>(null);
  const [points, setPoints] = useState<{ key: string; facilities: PointLayer | null; settlements: PointLayer | null } | null>(null);

  const setParam = useCallback(
    (changes: Record<string, string | null>) => {
      const p = new URLSearchParams(params);
      for (const [k, v] of Object.entries(changes)) {
        if (v === null || v === "") p.delete(k);
        else p.set(k, v);
      }
      router.push(`${pathname}?${p}`, { scroll: false });
    },
    [params, pathname, router],
  );

  useEffect(() => {
    clientApi<IndicatorInfo[]>("/api/v1/indicators").then(setCatalogue).catch(() => setCatalogue([]));
    clientApi<Sector[]>("/api/v1/sectors").then(setSectors).catch(() => setSectors([]));
  }, []);

  useEffect(() => {
    if (requested) return;
    clientApi<AreaSummary[]>("/api/v1/areas?level=country")
      .then((rows) => {
        if (rows.length === 0) setRootError("No country boundary is loaded. Run `connectly bootstrap`.");
        else setRootId(rows[0].id);
      })
      .catch((e) => setRootError(e instanceof ApiError ? e.message : String(e)));
  }, [requested]);

  const currentId = requested ?? rootId;

  useEffect(() => {
    if (currentId == null) return;
    let stale = false;
    loadArea(currentId)
      .then((d) => {
        if (stale) return;
        setResult({ id: currentId, data: d });
        setFilter("");
      })
      .catch((e) => {
        if (!stale) setResult({ id: currentId, error: e instanceof ApiError ? e.message : String(e) });
      });
    return () => {
      stale = true;
    };
  }, [currentId]);

  const loading = result?.id !== currentId;
  const data = result && "data" in result ? result.data : null;
  const error = rootError ?? (result && "error" in result && !loading ? result.error : null);
  const area = data?.area;
  const childLevel = area?.child_level && area.child_count > 0 ? area.child_level : null;

  // Indicators that have values at the level being coloured, filtered by sector.
  const available = useMemo(
    () =>
      catalogue.filter(
        (i) => childLevel && (i.values_by_level[childLevel] ?? 0) > 0 && (!sector || i.sector === sector || i.sector === null),
      ),
    [catalogue, childLevel, sector],
  );
  const unavailable = useMemo(
    () => catalogue.filter((i) => childLevel && !available.includes(i) && (!sector || i.sector === sector)),
    [catalogue, available, childLevel, sector],
  );
  const indicator =
    indicatorParam === "none"
      ? null
      : (available.find((i) => i.code === indicatorParam) ??
        available.find((i) => i.code === "population.density_per_km2") ??
        available[0] ??
        null);

  const choroKey = indicator && area && childLevel ? `${indicator.code}|${childLevel}|${area.id}` : null;
  useEffect(() => {
    if (!choroKey) return;
    const [code, level, parent] = choroKey.split("|");
    let stale = false;
    clientApi<ChoroplethResponse>(`/api/v1/choropleth?indicator=${code}&level=${level}&parent_id=${parent}`)
      .then((d) => !stale && setChoro({ key: choroKey, data: d }))
      .catch(() => !stale && setChoro(null));
    return () => {
      stale = true;
    };
  }, [choroKey]);
  const choroData = choro && choro.key === choroKey ? choro.data : null;

  const facilityKind = sector ? SECTOR_FACILITY_KIND[sector] : undefined;
  const pointsAllowed = area && area.level !== "country";
  const pointsKey =
    pointsAllowed && (showFacilities || showSettlements)
      ? `${area.id}|${showFacilities ? (facilityKind ?? "all") : "-"}|${showSettlements ? 1 : 0}`
      : null;
  useEffect(() => {
    if (!pointsKey) return;
    const [id, fac, set] = pointsKey.split("|");
    let stale = false;
    Promise.all([
      fac !== "-"
        ? clientApi<PointsResponse>(`/api/v1/geojson/points?area_id=${id}&layer=facilities${fac !== "all" ? `&kind=${fac}` : ""}`)
        : Promise.resolve(null),
      set === "1" ? clientApi<PointsResponse>(`/api/v1/geojson/points?area_id=${id}&layer=settlements`) : Promise.resolve(null),
    ])
      .then(([f, s]) => {
        if (stale) return;
        setPoints({
          key: pointsKey,
          facilities: f ? { data: f, attribution: f.attribution } : null,
          settlements: s ? { data: s, attribution: s.attribution } : null,
        });
      })
      .catch(() => !stale && setPoints(null));
    return () => {
      stale = true;
    };
  }, [pointsKey]);
  const pointData = points && points.key === pointsKey ? points : null;

  const choropleth: Choropleth | null = useMemo(() => {
    if (!choroData) return null;
    return {
      values: new Map(choroData.values.map((v) => [v.id, v.value])),
      ...classes(choroData.quintile_breaks),
      format: (v: number) => formatValue(v, choroData.indicator.unit),
    };
  }, [choroData]);

  const select = useCallback((id: number) => setParam({ area: String(id) }), [setParam]);
  const onSelectPoint = useCallback(
    (layer: "facilities" | "settlements", id: number) => {
      if (layer === "settlements") router.push(`/settlements/${id}`);
    },
    [router],
  );

  const visibleChildren = useMemo(() => {
    const f = filter.trim().toLowerCase();
    return (data?.children ?? []).filter((c) => !f || c.name.toLowerCase().includes(f));
  }, [data, filter]);

  if (error) return <ErrorBox message={error} />;

  return (
    <div className="grid gap-4 lg:grid-cols-[380px_1fr]">
      <aside className="space-y-4">
        <nav className="flex flex-wrap items-center gap-1 text-sm" aria-label="Breadcrumb">
          {area?.breadcrumbs.map((b, i) => (
            <span key={b.id} className="flex items-center gap-1">
              {i > 0 && <span className="text-muted">/</span>}
              {b.id === area.id ? (
                <span className="font-medium">{b.name}</span>
              ) : (
                <button className="text-brand hover:underline" onClick={() => select(b.id)}>
                  {b.name}
                </button>
              )}
            </span>
          ))}
        </nav>

        {area && (
          <section className="rounded-lg border border-line bg-panel p-4">
            <div className="flex items-center gap-2">
              <Badge>{LEVEL_LABEL[area.level]}</Badge>
              {loading && <span className="text-xs text-muted">loading…</span>}
            </div>
            <h2 className="mt-2 text-xl font-semibold">{area.name}</h2>
            <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
              <dt className="text-muted">Area</dt>
              <dd className="tabular-nums">{formatNumber(area.area_km2)} km²</dd>
              {area.child_level && (
                <>
                  <dt className="text-muted">{LEVEL_PLURAL[area.child_level]}</dt>
                  <dd className="tabular-nums">{area.child_count > 0 ? area.child_count : "none loaded"}</dd>
                </>
              )}
              {area.aliases.length > 0 && (
                <>
                  <dt className="text-muted">Also known as</dt>
                  <dd>{area.aliases.join(", ")}</dd>
                </>
              )}
            </dl>
            {area.level !== "country" && (
              <Link
                href={`/areas/${area.id}`}
                className="mt-4 inline-flex rounded-md bg-brand px-3 py-1.5 text-sm font-medium text-white hover:bg-brand-strong"
              >
                Open {area.level === "ward" ? "community" : LEVEL_LABEL[area.level]} profile
              </Link>
            )}
            {area.notices.length > 0 && (
              <div className="mt-4 space-y-2">
                {area.notices.map((n) => (
                  <NoticeBox key={n.code} notice={n} />
                ))}
              </div>
            )}
            <details className="mt-4">
              <summary className="cursor-pointer text-xs font-medium text-muted">Boundary source</summary>
              <div className="mt-2">
                <Provenance dataset={area.dataset} />
              </div>
            </details>
          </section>
        )}

        <section className="space-y-3 rounded-lg border border-line bg-panel p-4" aria-label="Map layers">
          <div>
            <label htmlFor="sector" className="mb-1 block text-xs font-medium text-muted">
              Sector
            </label>
            <select
              id="sector"
              value={sector}
              onChange={(e) => setParam({ sector: e.target.value || null, indicator: null })}
              className="w-full rounded-md border border-line bg-panel px-2 py-1.5 text-sm"
            >
              <option value="">All sectors</option>
              {sectors.map((s) => (
                <option key={s.code} value={s.code}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>
          {childLevel ? (
            <div>
              <label htmlFor="indicator" className="mb-1 block text-xs font-medium text-muted">
                Colour {LEVEL_PLURAL[childLevel].toLowerCase()} by
              </label>
              <select
                id="indicator"
                value={indicator?.code ?? "none"}
                onChange={(e) => setParam({ indicator: e.target.value })}
                className="w-full rounded-md border border-line bg-panel px-2 py-1.5 text-sm"
              >
                <option value="none">Nothing (outlines only)</option>
                {available.map((i) => (
                  <option key={i.code} value={i.code}>
                    {i.name}
                  </option>
                ))}
                {unavailable.length > 0 && (
                  <optgroup label={`No values at ${LEVEL_LABEL[childLevel]} level yet`}>
                    {unavailable.map((i) => (
                      <option key={i.code} value={i.code} disabled>
                        {i.name}
                      </option>
                    ))}
                  </optgroup>
                )}
              </select>
              {indicator && choroData && choropleth && <Legend data={choroData} stops={choropleth.stops} colors={choropleth.colors} />}
            </div>
          ) : (
            <p className="text-xs text-muted">This area has no smaller areas to colour.</p>
          )}
          <fieldset className="space-y-1.5">
            <legend className="mb-1 text-xs font-medium text-muted">Points</legend>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                disabled={!pointsAllowed}
                checked={showFacilities}
                onChange={(e) => setParam({ facilities: e.target.checked ? "1" : null })}
                className="h-4 w-4 accent-[var(--color-brand)]"
              />
              <span className="inline-block h-2.5 w-2.5 rounded-full border border-white bg-brand ring-1 ring-brand" />
              {facilityKind ? FACILITY_KIND_LABEL[facilityKind] : "All facilities"}
              {pointData?.facilities && <span className="text-xs text-muted">({pointData.facilities.data.features.length})</span>}
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                disabled={!pointsAllowed}
                checked={showSettlements}
                onChange={(e) => setParam({ settlements: e.target.checked ? "1" : null })}
                className="h-4 w-4 accent-[var(--color-brand)]"
              />
              <span className="inline-block h-2.5 w-2.5 rounded-full bg-gold" />
              Settlements
              {pointData?.settlements && <span className="text-xs text-muted">({pointData.settlements.data.features.length})</span>}
            </label>
            {!pointsAllowed && <p className="text-xs text-muted">Choose a state to show points.</p>}
            {pointData && (pointData.facilities?.data.features.length === 0 || pointData.settlements?.data.features.length === 0) && (
              <p className="text-xs text-muted">
                No points loaded for this area. Facility and settlement files are loaded locally;
                see the Data sources page.
              </p>
            )}
          </fieldset>
        </section>

        {childLevel && (
          <section className="rounded-lg border border-line bg-panel">
            <div className="border-b border-line p-3">
              <label className="sr-only" htmlFor="area-filter">
                Filter {LEVEL_PLURAL[childLevel]}
              </label>
              <input
                id="area-filter"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                placeholder={`Filter ${area?.child_count} ${LEVEL_PLURAL[childLevel].toLowerCase()}`}
                className="w-full rounded-md border border-line bg-paper px-3 py-1.5 text-sm outline-none focus:border-brand"
              />
            </div>
            <ul className="max-h-[420px] divide-y divide-line overflow-y-auto">
              {visibleChildren.map((c) => {
                const v = choropleth?.values.get(c.id);
                return (
                  <li key={c.id}>
                    <button onClick={() => select(c.id)} className="flex w-full items-center justify-between gap-3 px-4 py-2 text-left text-sm hover:bg-paper">
                      <span>{c.name}</span>
                      <span className="text-xs tabular-nums text-muted">
                        {choropleth ? (v === undefined ? "no data" : choropleth.format(v)) : `${formatNumber(c.area_km2)} km²`}
                      </span>
                    </button>
                  </li>
                );
              })}
              {visibleChildren.length === 0 && <li className="px-4 py-3 text-sm text-muted">No match.</li>}
            </ul>
          </section>
        )}
      </aside>

      <section className="relative order-first overflow-hidden rounded-lg border border-line bg-panel lg:order-none lg:min-h-[680px]">
        <AreaMap
          context={data?.outline ?? null}
          subAreas={data?.childShapes ?? null}
          bbox={area?.bbox ?? null}
          choropleth={choropleth}
          facilities={pointData?.facilities ?? null}
          settlements={pointData?.settlements ?? null}
          onSelect={select}
          onSelectPoint={onSelectPoint}
        />
      </section>
    </div>
  );
}

function Legend({ data, stops, colors }: { data: ChoroplethResponse; stops: number[]; colors: string[] }) {
  const fmt = (v: number) => formatValue(v, data.indicator.unit);
  const first = data.values[0];
  const classes = colors.map((_, i) =>
    stops.length === 0
      ? "all values"
      : i === 0
        ? `below ${fmt(stops[0])}`
        : i === stops.length
          ? `${fmt(stops[i - 1])} and above`
          : `${fmt(stops[i - 1])} to below ${fmt(stops[i])}`,
  );
  return (
    <div className="mt-3 space-y-1.5 text-xs">
      <ul className="space-y-1">
        {classes.map((c, i) => (
          <li key={c} className="flex items-center gap-2">
            <span className="inline-block h-3 w-5 rounded-sm" style={{ background: colors[i] }} />
            {c}
          </li>
        ))}
      </ul>
      <p className="flex items-center gap-2">
        <span className="inline-block h-3 w-5 rounded-sm" style={{ background: NO_DATA }} />
        No value at this level ({data.missing.length})
      </p>
      {first && (
        <p className="text-muted">
          {first.value_type} · {first.verification_status.replace("_", " ")} · {first.period} · dataset {first.dataset}
          {data.indicator.higher_is_worse ? " · higher is worse" : ""}
        </p>
      )}
      <p className="text-muted">Classes are quintiles of the areas shown. Values from larger areas are never used to colour smaller ones.</p>
    </div>
  );
}
