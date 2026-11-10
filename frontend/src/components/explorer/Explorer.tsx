"use client";

import dynamic from "next/dynamic";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Badge, ErrorBox, NoticeBox, Provenance } from "@/components/ui";
import {
  ApiError,
  type AreaDetail,
  type AreaSummary,
  clientApi,
  type FeatureCollection,
  formatNumber,
  LEVEL_LABEL,
  LEVEL_PLURAL,
} from "@/lib/api";

// MapLibre touches `window`, so it only loads in the browser.
const AreaMap = dynamic(() => import("./AreaMap"), {
  ssr: false,
  loading: () => <div className="h-full min-h-[420px] w-full animate-pulse bg-paper" />,
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
      ? clientApi<FeatureCollection>(
          `/api/v1/geojson?level=${area.child_level}&parent_id=${id}`,
        )
      : Promise.resolve(null),
  ]);
  return { area, children, outline, childShapes };
}

export default function Explorer() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const requested = Number(params.get("area")) || null;

  const [rootId, setRootId] = useState<number | null>(null);
  const [rootError, setRootError] = useState<string | null>(null);
  // The last completed load, tagged with the area it belongs to.
  const [result, setResult] = useState<
    { id: number; data: Loaded } | { id: number; error: string } | null
  >(null);
  const [filter, setFilter] = useState("");

  // Find the country to start from when no area is in the URL.
  useEffect(() => {
    if (requested) return;
    clientApi<AreaSummary[]>("/api/v1/areas?level=country")
      .then((rows) => {
        if (rows.length === 0)
          setRootError("No country boundary is loaded. Run `connectly bootstrap`.");
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
        if (!stale) {
          setResult({ id: currentId, error: e instanceof ApiError ? e.message : String(e) });
        }
      });
    return () => {
      stale = true;
    };
  }, [currentId]);

  const loading = result?.id !== currentId;
  // Keep showing the previous area while the next one loads.
  const data = result && "data" in result ? result.data : null;
  const error = rootError ?? (result && "error" in result && !loading ? result.error : null);

  const select = useCallback(
    (id: number) => router.push(`${pathname}?area=${id}`, { scroll: false }),
    [router, pathname],
  );

  const visibleChildren = useMemo(() => {
    const f = filter.trim().toLowerCase();
    return (data?.children ?? []).filter((c) => !f || c.name.toLowerCase().includes(f));
  }, [data, filter]);

  if (error) return <ErrorBox message={error} />;

  const area = data?.area;
  return (
    <div className="grid gap-4 lg:grid-cols-[380px_1fr]">
      <aside className="space-y-4">
        {/* Breadcrumbs */}
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
                  <dd className="tabular-nums">
                    {area.child_count > 0 ? area.child_count : "none loaded"}
                  </dd>
                </>
              )}
              {area.aliases.length > 0 && (
                <>
                  <dt className="text-muted">Also known as</dt>
                  <dd>{area.aliases.join(", ")}</dd>
                </>
              )}
              {area.parent_overlap != null && area.level !== "country" && (
                <>
                  <dt className="text-muted">Inside parent</dt>
                  <dd className="tabular-nums">
                    {formatNumber(area.parent_overlap * 100, 1)}% (spatial check)
                  </dd>
                </>
              )}
            </dl>
            {area.notices.length > 0 && (
              <div className="mt-4 space-y-2">
                {area.notices.map((n) => (
                  <NoticeBox key={n.code} notice={n} />
                ))}
              </div>
            )}
            <details className="mt-4">
              <summary className="cursor-pointer text-xs font-medium text-muted">
                Boundary source
              </summary>
              <div className="mt-2">
                <Provenance dataset={area.dataset} />
              </div>
            </details>
          </section>
        )}

        {area?.child_level && area.child_count > 0 && (
          <section className="rounded-lg border border-line bg-panel">
            <div className="border-b border-line p-3">
              <label className="sr-only" htmlFor="area-filter">
                Filter {LEVEL_PLURAL[area.child_level]}
              </label>
              <input
                id="area-filter"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                placeholder={`Filter ${area.child_count} ${LEVEL_PLURAL[area.child_level].toLowerCase()}`}
                className="w-full rounded-md border border-line bg-paper px-3 py-1.5 text-sm outline-none focus:border-brand"
              />
            </div>
            <ul className="max-h-[420px] divide-y divide-line overflow-y-auto">
              {visibleChildren.map((c) => (
                <li key={c.id}>
                  <button
                    onClick={() => select(c.id)}
                    className="flex w-full items-center justify-between px-4 py-2 text-left text-sm hover:bg-paper"
                  >
                    <span>{c.name}</span>
                    <span className="text-xs tabular-nums text-muted">
                      {formatNumber(c.area_km2)} km²
                    </span>
                  </button>
                </li>
              ))}
              {visibleChildren.length === 0 && (
                <li className="px-4 py-3 text-sm text-muted">No match.</li>
              )}
            </ul>
          </section>
        )}
      </aside>

      <section className="overflow-hidden rounded-lg border border-line bg-panel lg:min-h-[640px]">
        <AreaMap
          context={data?.outline ?? null}
          subAreas={data?.childShapes ?? null}
          bbox={area?.bbox ?? null}
          onSelect={select}
        />
      </section>
    </div>
  );
}
