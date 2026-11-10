import Link from "next/link";
import { connection } from "next/server";
import { Suspense } from "react";

import { Badge, ErrorBox, PageHeader, Panel, Stat } from "@/components/ui";
import {
  ApiError,
  type DataGap,
  formatNumber,
  type Sector,
  serverApi,
  type Stats,
} from "@/lib/api";

export default function OverviewPage() {
  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <PageHeader
        title="Overview"
        lead="What the platform holds today. Every number is counted from the database at request time; nothing is estimated or illustrative."
      />
      <Suspense fallback={<p className="text-sm text-muted">Loading counts…</p>}>
        <Overview />
      </Suspense>
    </div>
  );
}

async function Overview() {
  await connection(); // always read fresh counts
  let stats: Stats, sectors: Sector[], gaps: DataGap[];
  try {
    [stats, sectors, gaps] = await Promise.all([
      serverApi<Stats>("/api/v1/stats"),
      serverApi<Sector[]>("/api/v1/sectors"),
      serverApi<DataGap[]>("/api/v1/data-gaps?status=open"),
    ]);
  } catch (e) {
    return <ErrorBox message={e instanceof ApiError ? e.message : "Could not load data."} />;
  }
  const a = stats.areas_by_level;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="States (incl. FCT)" value={formatNumber(a.state)} />
        <Stat label="Local Government Areas" value={formatNumber(a.lga)} />
        <Stat
          label="Wards"
          value={formatNumber(a.ward)}
          note={a.ward === 0 ? "Not loaded yet" : undefined}
        />
        <Stat
          label="Communities"
          value={stats.settlements == null ? "—" : formatNumber(stats.settlements)}
          note={stats.settlements == null ? "Planned for Milestone 2" : undefined}
        />
        <Stat
          label="Datasets loaded"
          value={formatNumber(stats.datasets_loaded)}
          note={`${stats.datasets_registered} registered`}
        />
        <Stat label="Indicators defined" value={formatNumber(stats.indicators_defined)} />
        <Stat
          label="Indicator values"
          value={formatNumber(stats.observations)}
          note={stats.observations === 0 ? "None ingested yet" : undefined}
        />
        <Stat label="Open data gaps" value={formatNumber(stats.open_data_gaps)} />
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_1.2fr]">
        <Panel title="Sectors">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted">
              <tr>
                <th className="pb-2 font-normal">Sector</th>
                <th className="pb-2 font-normal">Needs</th>
                <th className="pb-2 font-normal">Indicators</th>
                <th className="pb-2 font-normal">Values</th>
              </tr>
            </thead>
            <tbody>
              {sectors.map((s) => (
                <tr key={s.code} className="border-t border-line">
                  <td className="py-2">
                    <div className="flex flex-wrap items-center gap-2">
                      {s.name}
                      {s.is_priority && <Badge tone="good">priority</Badge>}
                    </div>
                  </td>
                  <td className="py-2 tabular-nums">{s.needs.length}</td>
                  <td className="py-2 tabular-nums">{s.indicator_count}</td>
                  <td className="py-2 tabular-nums">{s.observation_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-3 text-xs text-muted">
            Indicators are defined; their values arrive with Milestone 2 ingestion.
          </p>
        </Panel>

        <Panel
          title="Open data gaps"
          aside={
            <Link href="/data" className="text-xs text-brand hover:underline">
              All sources and gaps
            </Link>
          }
        >
          <ul className="divide-y divide-line">
            {gaps.map((g) => (
              <li key={g.code} className="py-2.5 first:pt-0 last:pb-0">
                <div className="flex flex-wrap items-center gap-2 text-sm font-medium">
                  {g.title}
                  {g.sector && <Badge>{g.sector}</Badge>}
                  {g.needs_field_verification && <Badge tone="warn">field verification</Badge>}
                </div>
                <p className="mt-0.5 text-xs text-muted">{g.description}</p>
              </li>
            ))}
          </ul>
        </Panel>
      </div>

      <p className="text-xs text-muted">
        Counted {new Date(stats.generated_at).toLocaleString("en-GB")}.
      </p>
    </div>
  );
}
