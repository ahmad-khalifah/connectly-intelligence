import Link from "next/link";
import { unstable_rethrow } from "next/navigation";
import { connection } from "next/server";
import { Suspense } from "react";

import { SectionLoader } from "@/components/brand";
import { Badge, ErrorBox, PageHeader, Panel, Stat } from "@/components/ui";
import CoverageTable from "@/components/CoverageTable";
import { ApiError, type DataGap, formatNumber, type NationalCoverage, type Sector, type Stats } from "@/lib/api";
import { serverApi } from "@/lib/server";

export default function OverviewPage() {
  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <PageHeader
        title="Overview"
        lead="What the platform holds today. Every number is counted from the database when this page loads; nothing is estimated or illustrative."
      />
      <Suspense fallback={<SectionLoader label="Counting" />}>
        <Overview />
      </Suspense>
    </div>
  );
}

const WORKFLOWS = [
  { href: "/intelligence", title: "Intelligence brief", text: "Everything known about a community and sector, with cited evidence." },
  { href: "/needs", title: "Needs assessment", text: "Which areas are least served, compared with similar areas." },
  { href: "/matching", title: "Technology matching", text: "Solutions ranked on eight criteria for one community." },
  { href: "/market-entry", title: "Market entry", text: "Where and how a product could start, from the evidence." },
];

async function Overview() {
  await connection(); // always read fresh counts
  let stats: Stats, sectors: Sector[], gaps: DataGap[], coverage: NationalCoverage;
  try {
    [stats, sectors, gaps, coverage] = await Promise.all([
      serverApi<Stats>("/api/v1/stats"),
      serverApi<Sector[]>("/api/v1/sectors"),
      serverApi<DataGap[]>("/api/v1/data-gaps?status=open"),
      serverApi<NationalCoverage>("/api/v1/coverage"),
    ]);
  } catch (e) {
    unstable_rethrow(e); // let sign-in redirects through
    return <ErrorBox message={e instanceof ApiError ? e.message : "Could not load data."} />;
  }
  const a = stats.areas_by_level;
  const total = coverage.states_total;
  const nationwide = coverage.layers.filter((l) => l.states_covered === total).length;
  const bySector = stats.observations_by_sector ?? {};
  const maxValues = Math.max(1, ...sectors.map((s) => bySector[s.code] ?? 0));

  return (
    <div className="space-y-6">
      <section className="relative overflow-hidden rounded-xl bg-brand p-6 text-white">
        <div aria-hidden className="absolute -right-16 -top-16 h-64 w-64 rounded-full border-[22px] border-white/5" />
        <div aria-hidden className="absolute -bottom-24 right-40 h-56 w-56 rounded-full border-[22px] border-gold/20" />
        <div className="relative">
          <div className="flex items-center gap-2 text-xs tracking-wide text-white/75">
            <span className="h-px w-6 bg-gold" /> National coverage
          </div>
          <h2 className="mt-2 text-2xl font-semibold">Nigeria: 36 states and the FCT</h2>
          <dl className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
            {[
              ["States", formatNumber(a.state)],
              ["LGAs", formatNumber(a.lga)],
              ["Wards", formatNumber(a.ward)],
              ["Evidence layers covering every state", `${nationwide} of ${coverage.layers.length}`],
            ].map(([k, v]) => (
              <div key={k}>
                <dt className="text-xs text-white/70">{k}</dt>
                <dd className="mt-0.5 text-xl font-semibold tabular-nums">{v}</dd>
              </div>
            ))}
          </dl>
          <ul className="mt-4 flex flex-wrap gap-2 text-xs">
            {coverage.layers.map((l) => (
              <li key={l.code} className={`rounded-full border px-2.5 py-1 ${l.states_covered === total ? "border-white/40 bg-white/10" : "border-gold/50 text-white/85"}`}>
                {l.label}: {l.states_covered}/{total} states
              </li>
            ))}
          </ul>
          <div className="mt-5 flex flex-wrap gap-2 text-sm">
            <Link href="/explorer" className="rounded-md bg-white px-3 py-1.5 font-medium text-brand hover:bg-gold-soft">Explore Nigeria</Link>
            <Link href="/needs?level=lga" className="rounded-md border border-white/40 px-3 py-1.5 hover:bg-white/10">Compare all 774 LGAs</Link>
            <a href="#coverage" className="rounded-md border border-white/40 px-3 py-1.5 hover:bg-white/10">Coverage by state</a>
          </div>
          <p className="mt-3 text-xs text-white/70">Layers that do not yet cover every state are listed with the states they cover. Population is a model estimate (unverified).</p>
        </div>
      </section>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {WORKFLOWS.map((w) => (
          <Link key={w.href} href={w.href} className="group rounded-lg border border-line bg-panel p-4 transition-colors hover:border-brand/40">
            <div className="font-semibold text-brand">{w.title} <span className="inline-block transition-transform group-hover:translate-x-0.5">→</span></div>
            <p className="mt-1 text-sm text-muted">{w.text}</p>
          </Link>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
        <Stat label="States (incl. FCT)" value={formatNumber(a.state)} />
        <Stat label="LGAs" value={formatNumber(a.lga)} />
        <Stat label="Wards" value={formatNumber(a.ward)} />
        <Stat label="Indicator values" value={formatNumber(stats.observations)} />
        <Stat label="Datasets loaded" value={formatNumber(stats.datasets_loaded)} note={`${stats.datasets_registered} registered`} />
        <Stat label="Open data gaps" value={formatNumber(stats.open_data_gaps)} />
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Solutions published" value={formatNumber(stats.solutions_published ?? 0)} note={`${stats.organisations_active ?? 0} approved organisations`} />
        <Stat label="Awaiting review" value={formatNumber(stats.solutions_awaiting_review ?? 0)} />
        <Stat label="Community claims" value={formatNumber(stats.claims ?? 0)} note={`${stats.claims_verified ?? 0} verified`} />
        <Stat label="Saved reports" value={formatNumber(stats.reports ?? 0)} />
      </div>

      <div id="coverage" className="scroll-mt-20">
        <Panel title="Data coverage by state" aside={<Link href="/data" className="text-xs text-brand hover:underline">Datasets and how to load them</Link>}>
          <CoverageTable coverage={coverage} />
        </Panel>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_1.2fr]">
        <Panel title="Evidence by sector">
          <ul className="space-y-3">
            {sectors.map((s) => {
              const n = bySector[s.code] ?? 0;
              return (
                <li key={s.code}>
                  <div className="flex items-center justify-between gap-2 text-sm">
                    <span className="flex items-center gap-2">
                      {s.name} {s.is_priority && <Badge tone="gold">priority</Badge>}
                    </span>
                    <span className="text-xs tabular-nums text-muted">{n ? `${formatNumber(n)} values` : "no values loaded"}</span>
                  </div>
                  <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-paper">
                    <div className="h-full rounded-full bg-brand" style={{ width: `${(n / maxValues) * 100}%` }} />
                  </div>
                </li>
              );
            })}
          </ul>
          <p className="mt-4 text-xs text-muted">
            General values (population, density, urban classification): {formatNumber(bySector.general ?? 0)}. Sector values arrive with the facility, settlement and survey datasets listed on the Data sources page.
          </p>
        </Panel>
        <Panel title="Open data gaps" aside={<Link href="/data" className="text-xs text-brand hover:underline">All sources and gaps</Link>}>
          <ul className="divide-y divide-line">
            {gaps.slice(0, 7).map((g) => (
              <li key={g.code} className="py-2.5 first:pt-0 last:pb-0">
                <div className="flex flex-wrap items-center gap-2 text-sm font-medium">
                  {g.title}
                  {g.needs_field_verification && <Badge tone="warn">field verification</Badge>}
                </div>
                <p className="mt-0.5 line-clamp-2 text-xs text-muted">{g.description}</p>
              </li>
            ))}
          </ul>
          {gaps.length > 7 && <p className="mt-3 text-xs text-muted">and {gaps.length - 7} more.</p>}
        </Panel>
      </div>
      <p className="text-xs text-muted">Counted {new Date(stats.generated_at).toLocaleString("en-GB")}.</p>
    </div>
  );
}
