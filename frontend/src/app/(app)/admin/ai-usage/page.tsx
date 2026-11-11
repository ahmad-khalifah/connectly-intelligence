import type { Metadata } from "next";
import { Suspense } from "react";

import { SectionLoader } from "@/components/brand";
import { Badge, PageHeader, Panel, Stat } from "@/components/ui";
import { formatNumber, type ResearchStatus, type ResearchUsage } from "@/lib/api";
import { requireRole, serverApi } from "@/lib/server";

export const metadata: Metadata = { title: "AI usage" };

interface Usage {
  today: ResearchUsage;
  days: { day: string; purpose: string; status: string; requests: number; tokens: number; search_queries: number }[];
  recent_errors: { at: string; purpose: string; status: string; http_status: number | null; error: string | null }[];
}

const PURPOSE: Record<string, string> = {
  web_research: "Web research (Google Search)",
  source_extraction: "Source analysis",
  summary: "Brief summaries",
};

export default function AIUsagePage() {
  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <PageHeader
        title="AI usage"
        lead="Every attempted Gemini request, including those stopped by Connectly's own limits before reaching Google. Only counts are kept: prompts and answers are not stored here. Days are US Pacific calendar days, when Google resets daily quotas."
      />
      <Suspense fallback={<SectionLoader label="Loading" />}>
        <Body />
      </Suspense>
    </div>
  );
}

async function Body() {
  await requireRole("admin");
  const [u, status] = await Promise.all([
    serverApi<Usage>("/api/v1/research/usage?days=30"),
    serverApi<ResearchStatus>("/api/v1/research/status"),
  ]);
  const t = u.today;
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Badge tone={status.configured ? "good" : "neutral"}>{status.configured ? "Gemini configured" : "Gemini not configured"}</Badge>
        <span className="text-muted">
          Search model {status.search_model}{status.search_model_allowed ? "" : " (not on the free-tier list: calls refused)"} · text model{" "}
          {status.text_model}{status.text_model_allowed ? "" : " (not on the free-tier list: calls refused)"}
        </span>
        {t.blocked_until && <Badge tone="bad">Paused by Google&apos;s limit until {new Date(t.blocked_until).toLocaleString("en-GB")}</Badge>}
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Web research today" value={`${t.searches} / ${t.search_limit}`} />
        <Stat label="Other requests today" value={`${t.requests} / ${t.request_limit}`} />
        <Stat label="Last minute" value={`${t.last_minute} / ${t.per_minute_limit}`} />
        <Stat label="Tokens today" value={formatNumber(t.tokens)} />
      </div>
      <Panel title="Last 30 days">
        {u.days.length === 0 ? (
          <p className="text-sm text-muted">No requests yet.</p>
        ) : (
          <div className="-mx-4 overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead className="text-left text-xs text-muted">
                <tr>
                  <th className="px-4 pb-2 font-normal">Day (Pacific)</th>
                  <th className="px-2 pb-2 font-normal">Purpose</th>
                  <th className="px-2 pb-2 font-normal">Outcome</th>
                  <th className="px-2 pb-2 text-right font-normal">Requests</th>
                  <th className="px-2 pb-2 text-right font-normal">Search queries</th>
                  <th className="px-4 pb-2 text-right font-normal">Tokens</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {u.days.map((d) => (
                  <tr key={`${d.day}-${d.purpose}-${d.status}`}>
                    <td className="px-4 py-1.5 tabular-nums">{d.day}</td>
                    <td className="px-2 py-1.5">{PURPOSE[d.purpose] ?? d.purpose}</td>
                    <td className="px-2 py-1.5">{d.status.replace("_", " ")}</td>
                    <td className="px-2 py-1.5 text-right tabular-nums">{formatNumber(d.requests)}</td>
                    <td className="px-2 py-1.5 text-right tabular-nums">{formatNumber(d.search_queries)}</td>
                    <td className="px-4 py-1.5 text-right tabular-nums">{formatNumber(d.tokens)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
      <Panel title="Recent errors and refusals">
        {u.recent_errors.length === 0 ? (
          <p className="text-sm text-muted">None.</p>
        ) : (
          <ul className="space-y-2 text-sm">
            {u.recent_errors.map((e, i) => (
              <li key={i}>
                <span className="tabular-nums text-muted">{new Date(e.at).toLocaleString("en-GB")}</span> · {PURPOSE[e.purpose] ?? e.purpose} · {e.status.replace("_", " ")}
                {e.http_status ? ` (HTTP ${e.http_status})` : ""}
                <div className="mt-0.5 break-words font-mono text-xs text-muted">{e.error}</div>
              </li>
            ))}
          </ul>
        )}
      </Panel>
      <p className="text-xs text-muted">
        Connectly calls only free-tier models and keeps its own daily and per-minute limits below Google&apos;s. When Google answers that a free-tier limit is reached, no further request is sent until the limit resets. Check the API key&apos;s Google Cloud project has no billing account linked: then Google cannot charge for it.
      </p>
    </div>
  );
}
