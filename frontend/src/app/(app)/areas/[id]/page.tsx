import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { SectionLoader } from "@/components/brand";
import { ClaimsPanel } from "@/components/profile/ClaimsPanel";
import { ValueBadges, ValueRow } from "@/components/profile/Values";
import { Badge, Panel } from "@/components/ui";
import {
  type AreaDetail,
  type AreaProfile,
  type AreaSummary,
  formatNumber,
  LEVEL_LABEL,
  LEVEL_PLURAL,
  CONFIDENCE_TONE,
  type NeedResult,
  type ProfileValue,
} from "@/lib/api";
import type { Vocabularies } from "@/lib/directory";
import { CLAIM_SECTOR, FACILITY_KIND_LABEL, SECTOR_FACILITY_KIND } from "@/lib/sectors";
import { currentUser, serverApi } from "@/lib/server";

export const metadata: Metadata = { title: "Community profile" };

export default function AreaProfilePage({ params }: PageProps<"/areas/[id]">) {
  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <Suspense fallback={<SectionLoader label="Loading profile" />}>
        <Profile params={params} />
      </Suspense>
    </div>
  );
}

function Fact({ label, children, note }: { label: string; children: React.ReactNode; note?: React.ReactNode }) {
  return (
    <div className="relative overflow-hidden rounded-lg border border-line bg-panel px-4 py-3">
      <span aria-hidden className="absolute inset-y-0 left-0 w-[3px] bg-gold" />
      <div className="text-xs text-muted">{label}</div>
      <div className="mt-1 text-lg font-semibold tabular-nums">{children}</div>
      {note && <div className="mt-1 text-xs text-muted">{note}</div>}
    </div>
  );
}

async function Profile({ params }: { params: PageProps<"/areas/[id]">["params"] }) {
  const { id } = await params;
  const areaId = Number(id) || 0;
  const [user, p, area, children, attributes, vocab] = await Promise.all([
    currentUser(),
    serverApi<AreaProfile>(`/api/v1/areas/${areaId}/profile`),
    serverApi<AreaDetail>(`/api/v1/areas/${areaId}`),
    serverApi<AreaSummary[]>(`/api/v1/areas/${areaId}/children`),
    serverApi<Record<string, string>>("/api/v1/claims/attributes"),
    serverApi<Vocabularies>("/api/v1/directory/vocabularies"),
  ]);
  const pop = p.population;
  const urban = p.urban_classification;
  const all = [...p.indicators, ...p.context_indicators];
  const shown = new Set(["population.modelled_total", "geo.urban_flag"]);
  const unitLabel = p.level === "ward" ? "community" : LEVEL_LABEL[p.level];
  const datasets = new Map<string, ProfileValue>();
  for (const v of all) datasets.set(v.dataset, v);

  return (
    <div className="space-y-8">
      <div>
        <nav aria-label="Breadcrumb" className="flex flex-wrap gap-1 text-sm text-muted">
          {area.breadcrumbs.map((b, i) => (
            <span key={b.id} className="flex items-center gap-1">
              {i > 0 && <span>/</span>}
              {b.id === area.id ? (
                <span className="text-ink">{b.name}</span>
              ) : b.level === "country" ? (
                <Link href="/explorer" className="hover:text-brand">{b.name}</Link>
              ) : (
                <Link href={`/areas/${b.id}`} className="hover:text-brand">{b.name}</Link>
              )}
            </span>
          ))}
        </nav>
        <div className="mt-2 flex flex-wrap items-end justify-between gap-4">
          <div>
            <Badge tone="brand">{p.level === "ward" ? "Ward (community)" : LEVEL_LABEL[p.level]}</Badge>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight">{p.name}</h1>
            <p className="mt-1 text-sm text-muted">
              {[p.lga && `${p.lga} LGA`, p.state && `${p.state} State`].filter(Boolean).join(", ")}
            </p>
          </div>
          <Link href={`/explorer?area=${p.id}`} className="rounded-md border border-line px-4 py-2 text-sm font-medium hover:border-brand/40">
            Show on map
          </Link>
        </div>
        {p.level === "ward" && (p.settlement_count ?? 0) === 0 && (
          <p className="mt-3 max-w-3xl text-xs text-muted">
            The ward is the smallest unit with loaded data, so it stands in for the communities inside it. Settlement-level profiles appear when GRID3 settlement data is loaded.
          </p>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
        <Fact
          label="Population"
          note={
            pop ? (
              <span className="flex flex-col gap-1">
                {pop.lower_bound != null && pop.upper_bound != null && (
                  <span>95% interval {formatNumber(pop.lower_bound)}–{formatNumber(pop.upper_bound)}</span>
                )}
                <span>
                  <ValueBadges v={pop} /> {pop.period}
                </span>
              </span>
            ) : (
              "No estimate loaded"
            )
          }
        >
          {pop?.value != null ? formatNumber(pop.value) : "—"}
        </Fact>
        <Fact label="Urban or rural" note={urban ? `${urban.dataset_title}, ${urban.period}` : "Not classified at this level"}>
          {urban?.value == null ? "—" : urban.value >= 1 ? "Urban" : "Rural"}
        </Fact>
        <Fact label="Area">{formatNumber(p.area_km2)} km²</Fact>
        <Fact label="Coordinates" note="A point inside the area">
          <span className="text-sm">
            {p.coordinates.lat.toFixed(4)}, {p.coordinates.lon.toFixed(4)}
          </span>
        </Fact>
        <Fact label="Settlements" note={(p.settlement_count ?? 0) === 0 ? "Not loaded" : undefined}>
          {p.settlement_count == null ? "—" : formatNumber(p.settlement_count)}
        </Fact>
        <Fact label="Last updated">
          <span className="text-sm">{p.last_updated ? new Date(p.last_updated).toLocaleDateString("en-GB") : "—"}</span>
        </Fact>
      </div>

      {(() => {
        const general = [
          ...p.indicators.filter((v) => v.sector === null && !shown.has(v.indicator)),
          ...p.context_indicators.filter((v) => v.sector === null),
        ];
        return general.length > 0 ? (
          <Panel title="Population and land">
            <ul className="grid gap-x-8 divide-y divide-line md:grid-cols-2 md:divide-y-0">
              {general.map((v) => (
                <ValueRow key={`${v.indicator}-${v.measured_at_level}`} v={v} />
              ))}
            </ul>
          </Panel>
        ) : null;
      })()}

      <section>
        <h2 className="mb-1 text-lg font-semibold">By sector</h2>
        <p className="mb-4 max-w-3xl text-sm text-muted">
          Each value shows how it was produced and where it comes from. State or LGA figures are marked as such and are never presented as this {unitLabel}&apos;s own value. Missing data is listed, not estimated.
        </p>
        <div className="grid gap-4 lg:grid-cols-2">
          {p.sectors.map((s) => {
            const own = p.indicators.filter((v) => v.sector === s.code && !shown.has(v.indicator));
            const ctx = p.context_indicators.filter((v) => v.sector === s.code);
            const kind = SECTOR_FACILITY_KIND[s.code];
            const fac = p.facilities.find((f) => f.kind === kind);
            const covered = kind ? p.facility_coverage[kind] : undefined;
            const missing = p.missing_indicators.filter((m) => m.sector === s.code);
            const claims = p.claims.filter((c) => CLAIM_SECTOR[c.attribute] === s.code);
            const empty = !own.length && !ctx.length && !fac && !claims.length;
            return (
              <Panel key={s.code} title={s.name} aside={s.is_priority ? <Badge tone="gold">priority</Badge> : undefined}>
                <div className="space-y-3">
                  {kind && (
                    <p className="text-sm">
                      <span className="text-muted">{FACILITY_KIND_LABEL[kind]}: </span>
                      {fac ? (
                        <strong className="tabular-nums">{formatNumber(fac.total)}</strong>
                      ) : covered ? (
                        <strong>0 in the loaded data</strong>
                      ) : (
                        <span className="text-muted">no facility data loaded for this state</span>
                      )}
                      {fac && <span className="text-xs text-muted"> ({fac.datasets.join(", ")})</span>}
                    </p>
                  )}
                  {(own.length > 0 || ctx.length > 0) && (
                    <ul className="divide-y divide-line">
                      {[...own, ...ctx].map((v) => (
                        <ValueRow key={`${v.indicator}-${v.measured_at_level}`} v={v} />
                      ))}
                    </ul>
                  )}
                  {claims.length > 0 && (
                    <ul className="space-y-1 text-sm">
                      {claims.map((c) => (
                        <li key={c.id}>
                          <span className="text-muted">{c.attribute_label}: </span>
                          {c.value_text} <ValueBadges v={c} />
                        </li>
                      ))}
                    </ul>
                  )}
                  {empty && <p className="text-sm text-muted">No data loaded for this sector here.</p>}
                  {missing.length > 0 && (
                    <details className="text-xs text-muted">
                      <summary className="cursor-pointer">Not available ({missing.length})</summary>
                      <ul className="mt-1 list-disc pl-5">
                        {missing.map((m) => (
                          <li key={m.code}>{m.name}</li>
                        ))}
                      </ul>
                    </details>
                  )}
                </div>
              </Panel>
            );
          })}
        </div>
      </section>

      {p.level !== "country" && (
        <Suspense fallback={<SectionLoader label="Scoring access gaps" />}>
          <Gaps areaId={p.id} />
        </Suspense>
      )}

      <section className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <Panel title="Community information">
          <ClaimsPanel
            subjectType="admin_area"
            subjectId={p.id}
            initial={p.claims}
            attributes={attributes}
            languages={vocab.languages}
            user={{ id: user.id, role: user.role }}
          />
        </Panel>
        <div className="space-y-4">
          {children.length > 0 && area.child_level && (
            <Panel title={`${LEVEL_PLURAL[area.child_level]} (${children.length})`}>
              <ul className="max-h-72 space-y-1 overflow-y-auto text-sm">
                {children.map((c) => (
                  <li key={c.id}>
                    <Link href={`/areas/${c.id}`} className="hover:text-brand">
                      {c.name}
                    </Link>
                  </li>
                ))}
              </ul>
            </Panel>
          )}
          <Panel title="Sources on this page">
            {datasets.size === 0 ? (
              <p className="text-sm text-muted">Only boundary data is loaded for this area.</p>
            ) : (
              <ul className="space-y-2 text-xs">
                {[...datasets.values()].map((v) => (
                  <li key={v.dataset}>
                    <div className="font-medium">{v.dataset_title}</div>
                    <div className="text-muted">
                      {v.licence ?? "Licence unknown"}
                      {v.attribution ? ` · ${v.attribution}` : ""}
                    </div>
                  </li>
                ))}
              </ul>
            )}
            <p className="mt-3 text-xs">
              <Link href="/data" className="text-brand hover:underline">
                All datasets and licences
              </Link>
            </p>
          </Panel>
          <Panel title="Known data gaps">
            <ul className="space-y-2 text-xs">
              {p.data_gaps.map((g) => (
                <li key={g.code}>
                  <div className="font-medium">
                    {g.title} {g.needs_field_verification && <Badge tone="warn">field verification</Badge>}
                  </div>
                  <div className="text-muted">{g.description}</div>
                </li>
              ))}
            </ul>
          </Panel>
        </div>
      </section>
      <p className="text-xs text-muted">
        Value types: measured (counted or surveyed), modelled (statistical model), derived (computed here from other values), estimate, assumption. Verification: whether a person has checked the value against its source or in the field.
      </p>
    </div>
  );
}

interface AreaNeeds {
  level: string;
  sectors: {
    sector: string;
    sector_name: string;
    status: string;
    scope: { id: number; name: string };
    areas_scored: number;
    result: NeedResult | null;
    message: string | null;
  }[];
}

async function Gaps({ areaId }: { areaId: number }) {
  const n = await serverApi<AreaNeeds>(`/api/v1/needs/areas/${areaId}`);
  return (
    <Panel title="Technology access gaps" aside={<Link href="/needs/method" className="text-xs text-brand hover:underline">Method</Link>}>
      <p className="mb-3 text-xs text-muted">Compared with similar areas in the same state (states with all states). 100 = least served.</p>
      <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {n.sectors.map((s) => {
          const r = s.result;
          return (
            <li key={s.sector} className="rounded-md border border-line p-3">
              <div className="text-xs text-muted">{s.sector_name}</div>
              {r && r.score !== null ? (
                <>
                  <div className="mt-1 flex items-baseline gap-2">
                    <span className="text-2xl font-semibold tabular-nums">{Math.round(r.score)}</span>
                    <span className="text-xs text-muted">rank {r.rank} of {s.areas_scored}</span>
                  </div>
                  <Badge tone={CONFIDENCE_TONE[r.confidence_label]}>{r.confidence_label} confidence</Badge>
                  {r.components[0] && <p className="mt-2 text-xs">{r.components[0].statement}</p>}
                </>
              ) : (
                <p className="mt-1 text-xs text-muted">
                  {s.status === "no_model" ? "No open indicator for this sector." : "Not enough data loaded to score."}
                </p>
              )}
              <Link href={`/needs?sector=${s.sector}&level=${n.level}&scope=${s.scope.id}`} className="mt-2 inline-block text-xs text-brand hover:underline">Compare</Link>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}
