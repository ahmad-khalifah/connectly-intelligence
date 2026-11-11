import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { SectionLoader } from "@/components/brand";
import { Badge, PageHeader, Panel, Stat } from "@/components/ui";
import { formatNumber, type Stats } from "@/lib/api";
import { requireRole, serverApi } from "@/lib/server";

export const metadata: Metadata = { title: "Administration" };

interface Run {
  id: number;
  dataset_key: string | null;
  dataset_title: string | null;
  started_at: string;
  finished_at: string | null;
  status: string;
  rows_read: number | null;
  rows_loaded: number | null;
  rows_rejected: number | null;
  warnings: string[] | null;
  error: string | null;
}

export default function AdminPage() {
  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <PageHeader title="Administration" />
      <Suspense fallback={<SectionLoader label="Loading" />}>
        <Body />
      </Suspense>
    </div>
  );
}

async function Body() {
  await requireRole("admin");
  const [stats, runs] = await Promise.all([serverApi<Stats>("/api/v1/stats"), serverApi<Run[]>("/api/v1/ingest/runs?limit=30")]);
  const links = [
    { href: "/admin/users", title: "Users", text: "Accounts, roles and temporary passwords" },
    { href: "/admin/audit", title: "Audit log", text: "Every sign-in and change" },
    { href: "/admin/ai-usage", title: "AI usage", text: "Gemini requests, tokens, limits and errors" },
    { href: "/directory?status=submitted", title: "Directory review", text: `${stats.solutions_awaiting_review ?? 0} solutions awaiting review` },
    { href: "/data", title: "Datasets and gaps", text: `${stats.datasets_loaded} loaded, ${stats.open_data_gaps} open gaps` },
  ];
  return (
    <div className="space-y-6">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {links.map((l) => (
          <Link key={l.href} href={l.href} className="rounded-lg border border-line bg-panel p-4 hover:border-brand/40">
            <div className="font-semibold text-brand">{l.title}</div>
            <div className="mt-1 text-sm text-muted">{l.text}</div>
          </Link>
        ))}
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Community claims" value={formatNumber(stats.claims)} note={`${stats.claims_verified ?? 0} verified`} />
        <Stat label="Organisations (approved)" value={formatNumber(stats.organisations_active ?? 0)} />
        <Stat label="Solutions published" value={formatNumber(stats.solutions_published ?? 0)} />
        <Stat label="Saved reports" value={formatNumber(stats.reports ?? 0)} />
      </div>
      <Panel title="Recent dataset loads">
        <p className="mb-3 text-xs text-muted">Datasets are loaded with the command line (see docs/data-ingestion.md); this is the record of each load.</p>
        <div className="-mx-4 overflow-x-auto">
          <table className="w-full min-w-[760px] text-sm">
            <thead className="text-left text-xs text-muted">
              <tr>
                <th className="px-4 pb-2 font-normal">Started</th>
                <th className="px-2 pb-2 font-normal">Dataset</th>
                <th className="px-2 pb-2 font-normal">Status</th>
                <th className="px-2 pb-2 font-normal">Rows read / loaded / rejected</th>
                <th className="px-4 pb-2 font-normal">Notes</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id} className="border-t border-line align-top">
                  <td className="whitespace-nowrap px-4 py-2 text-xs text-muted">{new Date(r.started_at).toLocaleString("en-GB")}</td>
                  <td className="px-2 py-2">{r.dataset_title ?? r.dataset_key ?? "—"}</td>
                  <td className="px-2 py-2"><Badge tone={r.status === "succeeded" ? "good" : r.status === "failed" ? "bad" : "neutral"}>{r.status}</Badge></td>
                  <td className="px-2 py-2 tabular-nums text-xs">{[r.rows_read, r.rows_loaded, r.rows_rejected].map((v) => v ?? "—").join(" / ")}</td>
                  <td className="px-4 py-2 text-xs text-muted">{r.error ?? (r.warnings ?? []).slice(0, 3).join("; ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
