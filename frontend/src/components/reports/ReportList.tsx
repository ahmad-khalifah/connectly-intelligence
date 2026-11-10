"use client";

import { useState } from "react";

import { Badge, Panel } from "@/components/ui";
import { sendJson } from "@/lib/api";

const KIND = { brief: "Intelligence brief", needs: "Needs assessment", matching: "Technology matching", market_entry: "Market entry" };

interface Row {
  id: number;
  kind: keyof typeof KIND;
  title: string;
  created_at: string;
  created_by: string | null;
}

export function ReportList({ initial, showAuthor }: { initial: Row[]; showAuthor: boolean }) {
  const [rows, setRows] = useState(initial);
  if (rows.length === 0)
    return (
      <div className="rounded-lg border border-dashed border-line bg-panel px-6 py-10 text-center text-sm text-muted">
        No reports saved yet.
      </div>
    );
  return (
    <Panel>
      <ul className="divide-y divide-line">
        {rows.map((r) => (
          <li key={r.id} className="flex flex-wrap items-center justify-between gap-3 py-3 first:pt-0 last:pb-0">
            <div>
              <div className="font-medium">{r.title}</div>
              <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-muted">
                <Badge tone="brand">{KIND[r.kind]}</Badge>
                {new Date(r.created_at).toLocaleString("en-GB")}
                {showAuthor && r.created_by && <span>· {r.created_by}</span>}
              </div>
            </div>
            <div className="flex items-center gap-4 text-sm">
              <a href={`/api/backend/api/v1/reports/${r.id}/pdf`} className="font-medium text-brand hover:underline">
                Download PDF
              </a>
              <button
                className="text-bad hover:underline"
                onClick={async () => {
                  if (!confirm(`Delete "${r.title}"?`)) return;
                  await sendJson(`/api/v1/reports/${r.id}`, "DELETE");
                  setRows((x) => x.filter((y) => y.id !== r.id));
                }}
              >
                Delete
              </button>
            </div>
          </li>
        ))}
      </ul>
    </Panel>
  );
}
