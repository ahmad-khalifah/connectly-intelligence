"use client";

import Link from "next/link";
import { useState } from "react";

import { Button, Field, FormMessage, inputClass } from "@/components/forms";
import { AreaPicker } from "@/components/matching/AreaPicker";
import { ValueBadges } from "@/components/profile/Values";
import { Badge, Panel } from "@/components/ui";
import { ApiError, BRIEF_SECTION, type IntelligenceBrief, ITEM_KIND, sendJson } from "@/lib/api";

export function Intelligence({
  sectors,
  ai,
}: {
  sectors: { code: string; name: string }[];
  ai: { enabled: boolean; model: string | null; provider: string };
}) {
  const [areaId, setAreaId] = useState<number | null>(null);
  const [sector, setSector] = useState("health");
  const [question, setQuestion] = useState("");
  const [summarise, setSummarise] = useState(ai.enabled);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [b, setB] = useState<IntelligenceBrief | null>(null);

  async function run(e: React.FormEvent) {
    e.preventDefault();
    if (!areaId) return setError("Choose an area.");
    setBusy(true);
    setError(null);
    try {
      setB(await sendJson<IntelligenceBrief>("/api/v1/intelligence/brief", "POST", { area_id: areaId, sector, question: question.trim() || null, summarise }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The brief could not be built.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <Panel title="Area and sector">
        <form onSubmit={run} className="space-y-4">
          <AreaPicker onChange={setAreaId} />
          <div className="grid gap-3 sm:grid-cols-[1fr_2fr]">
            <Field label="Sector" htmlFor="i-sector">
              <select id="i-sector" value={sector} onChange={(e) => setSector(e.target.value)} className={inputClass}>
                {sectors.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}
              </select>
            </Field>
            <Field label="Question (optional)" htmlFor="i-q" hint="Searches community information, data gaps and the directory">
              <input id="i-q" maxLength={500} value={question} onChange={(e) => setQuestion(e.target.value)} className={inputClass} />
            </Field>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" disabled={!ai.enabled} checked={summarise} onChange={(e) => setSummarise(e.target.checked)} className="h-4 w-4 accent-[var(--color-brand)]" />
            Add an AI summary {ai.enabled ? `(${ai.model}, self-hosted)` : "(no language model configured)"}
          </label>
          {error && <FormMessage tone="error">{error}</FormMessage>}
          <Button type="submit" busy={busy}>Build brief</Button>
        </form>
      </Panel>
      {b && <Brief b={b} />}
    </div>
  );
}

function Cites({ ids }: { ids: string[] }) {
  if (!ids.length) return null;
  return (
    <span className="ml-1 text-xs">
      {ids.map((id) => (
        <a key={id} href={`#${id}`} className="mr-1 rounded bg-paper px-1 text-brand hover:underline">{id}</a>
      ))}
    </span>
  );
}

function Brief({ b }: { b: IntelligenceBrief }) {
  const n = b.narrative;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-xl font-semibold">{b.sector_name}: {b.area.place}</h2>
        <Link href={`/areas/${b.area.id}`} className="text-sm text-brand hover:underline">Area profile</Link>
      </div>
      {n.status !== "skipped" && (
        <section className={`rounded-lg border p-4 ${n.status === "accepted" ? "border-brand/30 bg-brand-soft/50" : "border-line bg-panel"}`}>
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold">Summary</h3>
            {n.status === "accepted" && <Badge tone="bad">AI-generated · {n.model}</Badge>}
          </div>
          {n.text ? (
            <p className="mt-2 whitespace-pre-line text-sm">{n.text}</p>
          ) : null}
          {n.message && <p className="mt-2 text-xs text-muted">{n.message}</p>}
          {n.problems.length > 0 && (
            <ul className="mt-2 list-disc pl-5 text-xs text-muted">
              {n.problems.map((p) => <li key={p}>{p}</li>)}
            </ul>
          )}
        </section>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        {b.sections.map((s) => (
          <Panel key={s.key} title={BRIEF_SECTION[s.key] ?? s.key}>
            <ul className="space-y-2">
              {s.statements.map((st, i) => (
                <li key={i} className="text-sm">
                  <Badge tone={ITEM_KIND[st.kind].tone}>{ITEM_KIND[st.kind].label}</Badge> {st.text}
                  <Cites ids={st.cites} />
                </li>
              ))}
            </ul>
          </Panel>
        ))}
      </div>
      <Panel title={`Evidence (${b.evidence.length})`}>
        <ol className="space-y-2 text-sm">
          {b.evidence.map((e) => (
            <li key={e.id} id={e.id} className="scroll-mt-24 target:rounded target:bg-gold-soft">
              <span className="mr-2 font-mono text-xs text-brand">{e.id}</span>
              {e.text}
              <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-muted">
                {e.value_type && <ValueBadges v={{ value_type: e.value_type, verification_status: e.verification ?? "unverified" }} />}
                <span>{e.source}</span>
              </div>
            </li>
          ))}
        </ol>
      </Panel>
      <p className="text-xs text-muted">
        The brief is assembled from the platform&apos;s own data by fixed rules. A language model, when configured, only summarises the numbered evidence, and its summary is shown only if every sentence cites evidence and uses only numbers found in it.
      </p>
    </div>
  );
}
