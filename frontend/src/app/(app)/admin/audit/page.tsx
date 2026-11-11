import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { SectionLoader } from "@/components/brand";
import { PageHeader, Panel } from "@/components/ui";
import { requireRole, serverApi } from "@/lib/server";

export const metadata: Metadata = { title: "Audit log" };

interface Entry {
  id: number;
  created_at: string;
  actor: string;
  action: string;
  entity_type: string;
  entity_id: string | null;
  summary: string | null;
  changes: { before?: Record<string, unknown>; after?: Record<string, unknown> } | null;
  ip: string | null;
}

const TYPES = ["", "user", "claim", "organisation", "solution", "dataset", "report", "research_source", "research_finding"];

export default function AuditPage({ searchParams }: PageProps<"/admin/audit">) {
  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <PageHeader
        title="Audit log"
        lead="Every sign-in and every change made through the platform, newest first. Entries cannot be edited or deleted through the application."
      />
      <Suspense fallback={<SectionLoader label="Loading audit log" />}>
        <Entries searchParams={searchParams} />
      </Suspense>
    </div>
  );
}

function fmt(v: unknown): string {
  if (v === null || v === undefined) return "—";
  return typeof v === "string" ? v : JSON.stringify(v);
}

async function Entries({ searchParams }: { searchParams: PageProps<"/admin/audit">["searchParams"] }) {
  await requireRole("admin");
  const sp = await searchParams;
  const type = typeof sp.type === "string" ? sp.type : "";
  const before = typeof sp.before === "string" ? sp.before : "";
  const q = new URLSearchParams({ limit: "100" });
  if (type) q.set("entity_type", type);
  if (before) q.set("before", before);
  const entries = await serverApi<Entry[]>(`/api/v1/audit?${q}`);
  return (
    <Panel
      title="Entries"
      aside={
        <nav aria-label="Filter by record type" className="flex flex-wrap gap-1 text-xs">
          {TYPES.map((t) => (
            <Link
              key={t || "all"}
              href={t ? `/admin/audit?type=${t}` : "/admin/audit"}
              className={`rounded px-2 py-1 ${t === type ? "bg-brand text-white" : "text-muted hover:bg-paper"}`}
            >
              {t || "all"}
            </Link>
          ))}
        </nav>
      }
    >
      {entries.length === 0 ? (
        <p className="text-sm text-muted">No entries.</p>
      ) : (
        <div className="-mx-4 overflow-x-auto">
          <table className="w-full min-w-[820px] text-sm">
            <thead className="text-left text-xs text-muted">
              <tr>
                <th className="px-4 pb-2 font-normal">When</th>
                <th className="px-2 pb-2 font-normal">Who</th>
                <th className="px-2 pb-2 font-normal">Action</th>
                <th className="px-2 pb-2 font-normal">Record</th>
                <th className="px-4 pb-2 font-normal">Details</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => (
                <tr key={e.id} className="border-t border-line align-top">
                  <td className="whitespace-nowrap px-4 py-2 text-xs tabular-nums text-muted">
                    {new Date(e.created_at).toLocaleString("en-GB")}
                  </td>
                  <td className="px-2 py-2">{e.actor}</td>
                  <td className="px-2 py-2 font-medium">{e.action.replaceAll("_", " ")}</td>
                  <td className="px-2 py-2 text-xs">
                    {e.entity_type} {e.entity_id && <span className="text-muted">#{e.entity_id}</span>}
                  </td>
                  <td className="px-4 py-2 text-xs">
                    {e.summary && <div>{e.summary}</div>}
                    {e.changes?.after &&
                      Object.keys(e.changes.after).map((k) => (
                        <div key={k} className="text-muted">
                          {k}: {e.changes?.before && k in e.changes.before ? `${fmt(e.changes.before[k])} → ` : ""}
                          {fmt(e.changes?.after?.[k])}
                        </div>
                      ))}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {entries.length === 100 && (
        <Link
          href={`/admin/audit?${new URLSearchParams({ ...(type ? { type } : {}), before: entries[99].created_at })}`}
          className="mt-4 inline-block text-sm text-brand hover:underline"
        >
          Older entries
        </Link>
      )}
    </Panel>
  );
}
