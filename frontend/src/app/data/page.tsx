import { connection } from "next/server";
import { Suspense } from "react";

import { Badge, ErrorBox, PageHeader, Panel } from "@/components/ui";
import { ApiError, type DataGap, type Dataset, formatNumber, serverApi } from "@/lib/api";

export default function DataPage() {
  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <PageHeader
        title="Data sources"
        lead="Every dataset the platform knows about, with its licence, version and file checksum, followed by the data the platform needs but does not have."
      />
      <Suspense fallback={<p className="text-sm text-muted">Loading registry…</p>}>
        <Registry />
      </Suspense>
    </div>
  );
}

const STATUS_TONE: Record<string, "good" | "warn" | "neutral"> = {
  loaded: "good",
  failed: "warn",
  registered: "neutral",
  superseded: "neutral",
};

async function Registry() {
  await connection();
  let datasets: Dataset[], gaps: DataGap[];
  try {
    [datasets, gaps] = await Promise.all([
      serverApi<Dataset[]>("/api/v1/datasets"),
      serverApi<DataGap[]>("/api/v1/data-gaps"),
    ]);
  } catch (e) {
    return <ErrorBox message={e instanceof ApiError ? e.message : "Could not load data."} />;
  }

  return (
    <div className="space-y-6">
      <Panel title={`Datasets (${datasets.length})`}>
        <div className="space-y-4">
          {datasets.map((d) => (
            <article key={d.key} className="rounded-md border border-line p-3">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-sm font-semibold">{d.title}</h3>
                <Badge tone={STATUS_TONE[d.status] ?? "neutral"}>{d.status}</Badge>
                {d.level && <Badge>{d.level}</Badge>}
              </div>
              <dl className="mt-2 grid gap-x-4 gap-y-1 text-xs sm:grid-cols-[10rem_1fr]">
                <dt className="text-muted">Source</dt>
                <dd>{d.source_name}</dd>
                {d.distributor && (
                  <>
                    <dt className="text-muted">Distributed by</dt>
                    <dd>{d.distributor}</dd>
                  </>
                )}
                <dt className="text-muted">Version</dt>
                <dd>{d.version ?? "—"}</dd>
                <dt className="text-muted">Source last updated</dt>
                <dd>{d.source_update_text ?? d.publication_date ?? "—"}</dd>
                <dt className="text-muted">Licence</dt>
                <dd className="flex flex-wrap items-center gap-1.5">
                  {d.licence ?? "Unknown"}
                  <Badge tone={d.licence_verified ? "good" : "warn"}>
                    {d.licence_verified ? "verified" : "not verified"}
                  </Badge>
                  {d.commercial_use_allowed === true && <Badge>commercial use allowed</Badge>}
                  {d.commercial_use_allowed == null && (
                    <Badge tone="warn">commercial use undetermined</Badge>
                  )}
                </dd>
                {d.licence_evidence && (
                  <>
                    <dt className="text-muted">Licence evidence</dt>
                    <dd>{d.licence_evidence}</dd>
                  </>
                )}
                <dt className="text-muted">Records</dt>
                <dd className="tabular-nums">{formatNumber(d.record_count)}</dd>
                <dt className="text-muted">File</dt>
                <dd className="break-all font-mono">
                  {d.file_name ?? "—"}
                  {d.file_sha256 && <> · sha256 {d.file_sha256.slice(0, 16)}…</>}
                </dd>
                <dt className="text-muted">Retrieved</dt>
                <dd>{d.retrieved_at ? new Date(d.retrieved_at).toLocaleString("en-GB") : "—"}</dd>
                {d.method_summary && (
                  <>
                    <dt className="text-muted">Method</dt>
                    <dd>{d.method_summary}</dd>
                  </>
                )}
                {d.limitations && (
                  <>
                    <dt className="text-muted">Limitations</dt>
                    <dd>{d.limitations}</dd>
                  </>
                )}
                {d.landing_url && (
                  <>
                    <dt className="text-muted">Page</dt>
                    <dd className="break-all">
                      <a className="text-brand hover:underline" href={d.landing_url}>
                        {d.landing_url}
                      </a>
                    </dd>
                  </>
                )}
              </dl>
            </article>
          ))}
        </div>
      </Panel>

      <Panel title={`Data gaps (${gaps.length})`}>
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-muted">
            <tr>
              <th className="pb-2 pr-4 font-normal">Gap</th>
              <th className="hidden pb-2 pr-4 font-normal md:table-cell">Scope</th>
              <th className="hidden pb-2 pr-4 font-normal lg:table-cell">Possible sources</th>
              <th className="pb-2 font-normal">Status</th>
            </tr>
          </thead>
          <tbody>
            {gaps.map((g) => (
              <tr key={g.code} className="border-t border-line align-top">
                <td className="py-2.5 pr-4">
                  <div className="flex flex-wrap items-center gap-2 font-medium">
                    {g.title}
                    {g.sector && <Badge>{g.sector}</Badge>}
                    {g.needs_field_verification && (
                      <Badge tone="warn">field verification</Badge>
                    )}
                  </div>
                  <p className="mt-0.5 text-xs text-muted">{g.description}</p>
                </td>
                <td className="hidden py-2.5 pr-4 text-xs md:table-cell">{g.geographic_scope}</td>
                <td className="hidden py-2.5 pr-4 text-xs lg:table-cell">
                  {g.candidate_sources ?? "—"}
                </td>
                <td className="py-2.5">
                  <Badge tone={g.status === "resolved" ? "good" : "warn"}>{g.status}</Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </div>
  );
}
