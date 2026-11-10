"use client";

import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/forms";
import { ApiError, sendJson } from "@/lib/api";

/** Saves the analysis as a report (the server re-runs it from these parameters). */
export function SaveReport({ kind, params, label = "Save as report" }: { kind: string; params: Record<string, unknown>; label?: string }) {
  const [state, setState] = useState<{ busy?: boolean; id?: number; error?: string }>({});
  if (state.id)
    return (
      <span className="flex flex-wrap items-center gap-3 text-sm">
        <span className="text-good">Saved.</span>
        <a href={`/api/backend/api/v1/reports/${state.id}/pdf`} className="font-medium text-brand hover:underline">Download PDF</a>
        <Link href="/reports" className="text-brand hover:underline">All reports</Link>
      </span>
    );
  return (
    <span className="flex flex-wrap items-center gap-3">
      <Button
        variant="secondary"
        busy={state.busy}
        onClick={async () => {
          setState({ busy: true });
          try {
            const r = await sendJson<{ id: number }>("/api/v1/reports", "POST", { kind, params });
            setState({ id: r.id });
          } catch (e) {
            setState({ error: e instanceof ApiError ? e.message : "Could not save the report." });
          }
        }}
      >
        {label}
      </Button>
      {state.error && <span className="text-sm text-bad">{state.error}</span>}
    </span>
  );
}
