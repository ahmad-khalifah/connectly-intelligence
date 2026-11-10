import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { SectionLoader } from "@/components/brand";
import { ClaimsPanel } from "@/components/profile/ClaimsPanel";
import { ValueBadges } from "@/components/profile/Values";
import { Badge, Panel } from "@/components/ui";
import { type Claim, formatNumber } from "@/lib/api";
import type { Vocabularies } from "@/lib/directory";
import { FACILITY_KIND_LABEL } from "@/lib/sectors";
import { currentUser, serverApi } from "@/lib/server";

export const metadata: Metadata = { title: "Settlement" };

interface SettlementDetail {
  id: number;
  name: string | null;
  source_name: string | null;
  settlement_type: string | null;
  verification_status: string;
  source_note: string | null;
  lon: number;
  lat: number;
  ward_id: number | null;
  lga_id: number | null;
  state_id: number | null;
  updated_at: string;
  dataset: string | null;
  dataset_title: string | null;
  licence: string | null;
  attribution: string | null;
  extent_km2: number | null;
  nearest_facilities_within_50km: { kind: string; id: number; name: string | null; subtype: string | null; km: number; dataset: string }[];
  claims: Claim[];
}

export default function SettlementPage({ params }: PageProps<"/settlements/[id]">) {
  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <Suspense fallback={<SectionLoader label="Loading settlement" />}>
        <Body params={params} />
      </Suspense>
    </div>
  );
}

async function Body({ params }: { params: PageProps<"/settlements/[id]">["params"] }) {
  const { id } = await params;
  const [user, s, attributes, vocab] = await Promise.all([
    currentUser(),
    serverApi<SettlementDetail>(`/api/v1/settlements/${Number(id) || 0}`),
    serverApi<Record<string, string>>("/api/v1/claims/attributes"),
    serverApi<Vocabularies>("/api/v1/directory/vocabularies"),
  ]);
  const near = s.nearest_facilities_within_50km;
  return (
    <div className="space-y-6">
      <div>
        <Badge tone="brand">Settlement</Badge>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight">{s.name ?? "Unnamed settlement"}</h1>
        <div className="mt-2 flex flex-wrap gap-2 text-sm">
          {s.ward_id && <Link href={`/areas/${s.ward_id}`} className="text-brand hover:underline">Ward profile</Link>}
          {s.lga_id && <Link href={`/areas/${s.lga_id}`} className="text-brand hover:underline">LGA profile</Link>}
          <Link href={`/explorer?area=${s.ward_id ?? s.lga_id ?? ""}&settlements=1`} className="text-brand hover:underline">Show on map</Link>
        </div>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Record">
          <dl className="grid grid-cols-[8rem_1fr] gap-y-2 text-sm">
            <dt className="text-muted">Type</dt>
            <dd>{s.settlement_type ?? "Not stated"}</dd>
            <dt className="text-muted">Coordinates</dt>
            <dd className="tabular-nums">{s.lat.toFixed(5)}, {s.lon.toFixed(5)}</dd>
            <dt className="text-muted">Built-up extent</dt>
            <dd>{s.extent_km2 == null ? "Not loaded" : `${formatNumber(s.extent_km2, 2)} km²`}</dd>
            <dt className="text-muted">Verification</dt>
            <dd><ValueBadges v={{ value_type: "measured", verification_status: s.verification_status }} /></dd>
            <dt className="text-muted">Source</dt>
            <dd>{s.dataset_title ?? s.source_note ?? "—"}{s.licence && <span className="text-muted"> · {s.licence}</span>}</dd>
            {s.source_name && s.source_name !== s.name && (
              <>
                <dt className="text-muted">Name in source</dt>
                <dd>{s.source_name}</dd>
              </>
            )}
          </dl>
        </Panel>
        <Panel title="Nearest facilities (within 50 km)">
          {near.length === 0 ? (
            <p className="text-sm text-muted">No facilities within 50 km in the loaded data. Facility datasets may not be loaded for this state.</p>
          ) : (
            <table className="w-full text-sm">
              <tbody>
                {near.map((f) => (
                  <tr key={f.kind} className="border-t border-line first:border-t-0">
                    <td className="py-1.5 text-muted">{FACILITY_KIND_LABEL[f.kind] ?? f.kind}</td>
                    <td className="py-1.5">{f.name ?? f.subtype ?? "(unnamed)"}</td>
                    <td className="py-1.5 text-right tabular-nums">{formatNumber(f.km, 1)} km</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="mt-2 text-xs text-muted">Straight-line distance, not travel time.</p>
        </Panel>
      </div>
      <Panel title="Community information">
        <ClaimsPanel subjectType="settlement" subjectId={s.id} initial={s.claims} attributes={attributes} languages={vocab.languages} user={{ id: user.id, role: user.role }} />
      </Panel>
    </div>
  );
}
