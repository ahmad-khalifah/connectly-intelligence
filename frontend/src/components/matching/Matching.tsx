"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { Button, CheckboxGroup, Field, FormMessage, inputClass } from "@/components/forms";
import { Badge, Panel } from "@/components/ui";
import { ApiError, CONFIDENCE_TONE, type MatchResponse, type MatchResult, sendJson } from "@/lib/api";
import { AVAILABILITY_LABEL, type Availability, type Vocabularies } from "@/lib/directory";

import { SaveReport } from "@/components/reports/SaveReport";

import { AreaPicker } from "./AreaPicker";

export function Matching({ vocab }: { vocab: Vocabularies }) {
  const params = useSearchParams();
  const [areaId, setAreaId] = useState<number | null>(Number(params.get("area")) || null);
  const [sector, setSector] = useState(params.get("sector") ?? "health");
  const [need, setNeed] = useState(params.get("need") ?? "");
  const [groups, setGroups] = useState<string[]>([]);
  const [maxPrice, setMaxPrice] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<MatchResponse | null>(null);
  const needs = vocab.sectors.find((s) => s.code === sector)?.needs ?? [];

  async function run() {
    if (!areaId) return setError("Choose an area.");
    setBusy(true);
    setError(null);
    try {
      setResult(
        await sendJson<MatchResponse>("/api/v1/matching", "POST", {
          area_id: areaId,
          sector,
          need: need || null,
          target_groups: groups,
          max_price_ngn: maxPrice ? Number(maxPrice) : null,
        }),
      );
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Matching failed.");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    // Run once for a link that already names the area and sector.
    if (!params.get("area") || !params.get("sector")) return;
    const t = setTimeout(run, 0);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="space-y-6">
      <Panel title="What to match">
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            run();
          }}
        >
          <AreaPicker initialId={Number(params.get("area")) || null} onChange={setAreaId} />
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Sector" htmlFor="m-sector">
              <select id="m-sector" value={sector} onChange={(e) => { setSector(e.target.value); setNeed(""); }} className={inputClass}>
                {vocab.sectors.map((s) => (
                  <option key={s.code} value={s.code}>{s.name}</option>
                ))}
              </select>
            </Field>
            <Field label="Need" htmlFor="m-need" hint="Leave as automatic to use the area's gap evidence">
              <select id="m-need" value={need} onChange={(e) => setNeed(e.target.value)} className={inputClass}>
                <option value="">Automatic (from evidence)</option>
                {needs.map((n) => (
                  <option key={n.code} value={n.code}>{n.name}</option>
                ))}
              </select>
            </Field>
            <Field label="Highest acceptable price (₦, optional)" htmlFor="m-price">
              <input id="m-price" type="number" min={0} inputMode="numeric" value={maxPrice} onChange={(e) => setMaxPrice(e.target.value)} className={inputClass} />
            </Field>
          </div>
          <details>
            <summary className="cursor-pointer text-sm text-brand">Target groups (optional)</summary>
            <div className="mt-3">
              <CheckboxGroup legend="Who should benefit" name="groups" options={vocab.beneficiary_groups} value={groups} onChange={setGroups} columns={3} />
            </div>
          </details>
          {error && <FormMessage tone="error">{error}</FormMessage>}
          <Button type="submit" busy={busy}>Find matching solutions</Button>
        </form>
      </Panel>
      {result && (
        <>
          <SaveReport
            kind="matching"
            params={{ area_id: result.area.id, sector: result.sector, need: result.need, target_groups: groups, max_price_ngn: maxPrice ? Number(maxPrice) : null }}
          />
          <Results r={result} vocab={vocab} />
        </>
      )}
    </div>
  );
}

function Results({ r, vocab }: { r: MatchResponse; vocab: Vocabularies }) {
  return (
    <div className="space-y-4">
      <Panel title={`${r.sector_name} in ${r.area.name}`}>
        <div className="space-y-2 text-sm">
          <p>
            <span className="text-muted">Needs matched on: </span>
            {r.target_needs.length ? r.target_needs.map((n) => n.name).join(", ") : "none"}{" "}
            <Badge tone={r.needs_basis === "selected" ? "neutral" : "gold"}>
              {r.needs_basis === "selected" ? "chosen by you" : r.needs_basis === "gap_evidence" ? "from this area's gap evidence" : "not determined"}
            </Badge>
          </p>
          {r.gap_evidence.length > 0 && (
            <ul className="list-disc pl-5 text-xs text-muted">
              {r.gap_evidence.map((g) => (
                <li key={g}>{g}</li>
              ))}
            </ul>
          )}
          <p className="text-xs text-muted">
            Languages recorded for this area: {r.area_languages.length ? r.area_languages.map((l) => vocab.languages[l] ?? l).join(", ") : "none yet"}.{" "}
            <Link href={`/areas/${r.area.id}`} className="text-brand hover:underline">Area profile</Link>
          </p>
          {r.message && <p className="rounded-md border border-gold/40 bg-gold-soft px-3 py-2 text-gold-ink">{r.message}</p>}
        </div>
      </Panel>
      {r.results.map((m) => (
        <MatchCard key={m.solution.id} m={m} />
      ))}
      {r.excluded.length > 0 && (
        <Panel title={`Not recommended (${r.excluded.length})`}>
          <ul className="space-y-1 text-sm">
            {r.excluded.map((e) => (
              <li key={e.id}>
                <Link href={`/directory/solutions/${e.id}`} className="font-medium hover:text-brand">{e.name}</Link>{" "}
                <span className="text-muted">({e.organisation_name}): {e.reason}</span>
              </li>
            ))}
          </ul>
        </Panel>
      )}
      {r.results.length > 0 && (
        <p className="text-xs text-muted">
          Scores combine the eight criteria, weighted, over the criteria that could be judged. Ranking also weighs confidence: the share of criteria with data and whether the record is verified. Unknown criteria are shown, not guessed. These are suggestions from the directory&apos;s records, not endorsements.
        </p>
      )}
    </div>
  );
}

function MatchCard({ m }: { m: MatchResult }) {
  return (
    <article className="rounded-lg border border-line bg-panel">
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-line p-4">
        <div className="flex gap-3">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand text-sm font-semibold text-white">{m.rank}</span>
          <div>
            <Link href={`/directory/solutions/${m.solution.id}`} className="text-base font-semibold hover:text-brand">{m.solution.name}</Link>
            <div className="text-xs text-muted">{m.solution.organisation_name}</div>
            <p className="mt-1 text-sm">{m.solution.summary}</p>
          </div>
        </div>
        <div className="text-right">
          <div className="text-2xl font-semibold tabular-nums">{Math.round(m.score)}</div>
          <Badge tone={CONFIDENCE_TONE[m.confidence_label]}>{m.confidence_label} confidence</Badge>
          <div className="mt-1 text-xs text-muted">{m.criteria_known} of 8 criteria judged</div>
          {m.availability && <div className="text-xs text-muted">{AVAILABILITY_LABEL[m.availability as Availability]}</div>}
        </div>
      </header>
      <div className="grid gap-4 p-4 md:grid-cols-2">
        <div>
          <h4 className="text-xs font-medium uppercase tracking-wide text-good">Why it fits</h4>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-sm">
            {m.strengths.length ? m.strengths.map((s) => <li key={s}>{s}</li>) : <li className="text-muted">No criterion scored strongly.</li>}
          </ul>
        </div>
        <div>
          <h4 className="text-xs font-medium uppercase tracking-wide text-gold-ink">Check before acting</h4>
          <ul className="mt-1 list-disc space-y-1 pl-5 text-sm">
            {m.cautions.length ? m.cautions.map((s) => <li key={s}>{s}</li>) : <li className="text-muted">Nothing flagged.</li>}
          </ul>
        </div>
      </div>
      <details className="border-t border-line px-4 py-3">
        <summary className="cursor-pointer text-sm text-brand">All eight criteria</summary>
        <table className="mt-3 w-full text-sm">
          <tbody>
            {m.criteria.map((c) => (
              <tr key={c.key} className="border-t border-line align-top first:border-t-0">
                <td className="w-48 py-2 pr-3">
                  <div className="font-medium">{c.label}</div>
                  <div className="text-xs text-muted">weight {Math.round(c.weight * 100)}%</div>
                </td>
                <td className="w-28 py-2 pr-3">
                  {c.score === null ? (
                    <Badge>unknown</Badge>
                  ) : (
                    <span className="flex items-center gap-2">
                      <span className="h-1.5 w-14 overflow-hidden rounded-full bg-paper">
                        <span className="block h-full bg-brand" style={{ width: `${c.score * 100}%` }} />
                      </span>
                      <span className="text-xs tabular-nums">{Math.round(c.score * 100)}</span>
                    </span>
                  )}
                </td>
                <td className="py-2">
                  {c.reason}
                  {c.evidence.length > 0 && <div className="mt-0.5 text-xs text-muted">{c.evidence.join(" · ")}</div>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </article>
  );
}
