import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { SectionLoader } from "@/components/brand";
import { inputClass } from "@/components/forms";
import { ScoreMap } from "@/components/needs/ScoreMap";
import { SaveReport } from "@/components/reports/SaveReport";
import { ValueBadges } from "@/components/profile/Values";
import { Badge, PageHeader, Panel } from "@/components/ui";
import { type AreaSummary, CONFIDENCE_TONE, formatNumber, LEVEL_PLURAL, type NeedAssessment, type Sector } from "@/lib/api";
import { serverApi } from "@/lib/server";

export const metadata: Metadata = { title: "Needs assessment" };

export default function NeedsPage({ searchParams }: PageProps<"/needs">) {
  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <PageHeader
        title="Needs assessment"
        lead="Which areas are least served in a sector, compared with similar areas, on the evidence that is loaded. Every score shows the values behind it, how confident it is, and what is missing."
      />
      <Suspense fallback={<SectionLoader label="Scoring areas" />}>
        <Needs searchParams={searchParams} />
      </Suspense>
    </div>
  );
}

const one = (v: string | string[] | undefined) => (typeof v === "string" ? v : "");

async function Needs({ searchParams }: { searchParams: PageProps<"/needs">["searchParams"] }) {
  const sp = await searchParams;
  const [sectors, states, countries] = await Promise.all([
    serverApi<Sector[]>("/api/v1/sectors"),
    serverApi<AreaSummary[]>("/api/v1/areas?level=state"),
    serverApi<AreaSummary[]>("/api/v1/areas?level=country"),
  ]);
  const sector = one(sp.sector) || "health";
  const level = (["state", "lga", "ward"].includes(one(sp.level)) ? one(sp.level) : "lga") as "state" | "lga" | "ward";
  const nigeria = countries[0]?.id;
  const requested = Number(one(sp.scope)) || undefined;
  // States are compared across Nigeria; LGAs across Nigeria unless a state is chosen.
  // Ward comparisons (9,000+ areas nationally) need a state, which the user picks: no state
  // is ever chosen for them.
  const scopeId =
    level === "state" ? nigeria : level === "lga" ? (requested ?? nigeria) : requested !== nigeria ? requested : undefined;
  const r = scopeId
    ? await serverApi<NeedAssessment>(`/api/v1/needs/assessment?sector=${sector}&level=${level}&scope_id=${scopeId}`)
    : null;
  const scored = r ? r.areas.filter((a) => a.score !== null) : [];

  return (
    <div className="space-y-6">
      <form method="get" className="grid gap-3 rounded-lg border border-line bg-panel p-4 md:grid-cols-[1fr_1fr_1fr_auto] md:items-end">
        <div>
          <label htmlFor="sector" className="mb-1 block text-xs text-muted">Sector</label>
          <select id="sector" name="sector" defaultValue={sector} className={inputClass}>
            {sectors.map((s) => (
              <option key={s.code} value={s.code}>{s.name}</option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="level" className="mb-1 block text-xs text-muted">Compare</label>
          <select id="level" name="level" defaultValue={level} className={inputClass}>
            <option value="state">States (across Nigeria)</option>
            <option value="lga">LGAs</option>
            <option value="ward">Wards (within a state)</option>
          </select>
        </div>
        <div>
          <label htmlFor="scope" className="mb-1 block text-xs text-muted">Within (for LGAs and wards)</label>
          <select id="scope" name="scope" defaultValue={String(scopeId ?? "")} className={inputClass}>
            <option value={String(nigeria ?? "")}>Nigeria (all states)</option>
            {states.map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
        </div>
        <button type="submit" className="rounded-md bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-strong">Assess</button>
      </form>

      {!r ? (
        <p className="rounded-md border border-gold/40 bg-gold-soft px-3 py-2 text-sm text-gold-ink">
          Ward comparisons run within one state. Choose a state under &ldquo;Within&rdquo; and select Assess.
        </p>
      ) : (
        <>

      {scopeId && <SaveReport kind="needs" params={{ sector, level, scope_id: scopeId }} />}

      <div className="grid gap-4 lg:grid-cols-[1fr_1.1fr]">
        <Panel title={`${r.sector_name}: ${LEVEL_PLURAL[level].toLowerCase()} in ${r.scope.name}`}>
          {r.message && <p className="mb-3 rounded-md border border-gold/40 bg-gold-soft px-3 py-2 text-sm text-gold-ink">{r.message}</p>}
          {r.status !== "no_model" && (
            <>
              <p className="text-sm">
                <strong className="tabular-nums">{r.areas_scored}</strong> of {r.areas_in_scope} {LEVEL_PLURAL[level].toLowerCase()} have enough data for a score.
              </p>
              <h3 className="mt-4 text-xs font-medium uppercase tracking-wide text-muted">Evidence used</h3>
              <ul className="mt-2 divide-y divide-line text-sm">
                {r.indicators.map((i) => (
                  <li key={i.code} className="flex flex-wrap items-start justify-between gap-2 py-2">
                    <div>
                      <div>{i.name}</div>
                      {i.reason && <div className="text-xs text-muted">{i.reason}</div>}
                    </div>
                    <div className="flex items-center gap-2 text-xs">
                      <span className="text-muted">weight {Math.round(i.weight * 100)}%</span>
                      <Badge tone={i.used ? "good" : "neutral"}>{i.used ? `${i.areas_with_value} areas` : "not used"}</Badge>
                    </div>
                  </li>
                ))}
              </ul>
            </>
          )}
          <p className="mt-4 text-xs text-muted">
            Scores run from 0 to 100: the weighted share of comparable areas that are better served on each indicator. They are relative to the areas shown, not an absolute measure of need. Confidence combines how much of the evidence is available with how it was produced.{" "}
            <Link href="/needs/method" className="text-brand hover:underline">Method</Link>
          </p>
        </Panel>
        <section className="overflow-hidden rounded-lg border border-line bg-panel lg:min-h-[460px]">
          {scopeId && <ScoreMap level={level} scopeId={scopeId} scores={scored.map((a) => [a.id, a.score as number])} />}
        </section>
      </div>

      {r.areas.length > 0 && (
        <Panel title="Ranking">
          <ol className="divide-y divide-line">
            {r.areas.map((a) => (
              <li key={a.id} className="py-3">
                <details>
                  <summary className="grid cursor-pointer list-none grid-cols-[2.5rem_1fr_auto] items-center gap-3 sm:grid-cols-[2.5rem_1.2fr_1fr_8rem_6rem]">
                    <span className="text-sm tabular-nums text-muted">{a.rank ?? "–"}</span>
                    <span>
                      <Link href={`/areas/${a.id}`} className="font-medium hover:text-brand">{a.name}</Link>
                      {a.parent_name && level === "ward" && <span className="text-xs text-muted"> · {a.parent_name}</span>}
                    </span>
                    <span className="hidden sm:block">
                      {a.score !== null ? (
                        <span className="flex items-center gap-2">
                          <span className="h-2 flex-1 overflow-hidden rounded-full bg-paper">
                            <span className="block h-full rounded-full bg-brand" style={{ width: `${a.score}%` }} />
                          </span>
                          <span className="w-8 text-right text-sm font-semibold tabular-nums">{Math.round(a.score)}</span>
                        </span>
                      ) : (
                        <span className="text-xs text-muted">no score</span>
                      )}
                    </span>
                    <span className="text-right text-xs tabular-nums text-muted sm:text-left">
                      {a.population != null ? `${formatNumber(a.population)} people` : ""}
                    </span>
                    <span className="col-start-3 row-start-1 whitespace-nowrap text-right sm:col-auto sm:row-auto">
                      <Badge tone={CONFIDENCE_TONE[a.confidence_label]}>{a.confidence_label === "insufficient" ? "insufficient data" : `${a.confidence_label} confidence`}</Badge>
                    </span>
                  </summary>
                  <div className="mt-3 space-y-2 pl-0 text-sm sm:pl-[3.25rem]">
                    {a.components.map((c) => (
                      <div key={c.indicator}>
                        <p>{c.statement}</p>
                        <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-muted">
                          <ValueBadges v={c} /> {c.period} · {c.dataset} · weight {Math.round(c.weight * 100)}%
                        </p>
                      </div>
                    ))}
                    {a.missing.length > 0 && (
                      <p className="text-xs text-muted">
                        Missing: {a.missing.map((m) => `${m.name} (${m.reason})`).join("; ")}. Coverage {Math.round(a.coverage * 100)}% of the evidence weight.
                      </p>
                    )}
                  </div>
                </details>
              </li>
            ))}
          </ol>
          <p className="mt-3 text-xs text-muted">Population is the modelled estimate (WorldPop/NPC-derived, unverified), shown to help weigh results, not used in the score.</p>
        </Panel>
      )}
        </>
      )}
    </div>
  );
}
