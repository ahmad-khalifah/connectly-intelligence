"use client";

import Link from "next/link";
import { useState } from "react";

import { Button, CheckboxGroup, Field, FormMessage, FormSection, inputClass, UnknownSelect } from "@/components/forms";
import { Badge, Panel } from "@/components/ui";
import { ApiError, type AreaSummary, formatNumber, ITEM_KIND, type MarketEntryResult, sendJson } from "@/lib/api";
import type { Solution, Vocabularies } from "@/lib/directory";

export function MarketEntry({
  vocab,
  states,
  objectives,
  solutions,
}: {
  vocab: Vocabularies;
  states: AreaSummary[];
  objectives: Record<string, string>;
  solutions: Solution[];
}) {
  const [sector, setSector] = useState("health");
  const [need, setNeed] = useState("");
  const [solutionId, setSolutionId] = useState("");
  const [f, setF] = useState({
    product_name: "",
    industry: "",
    internet_requirement: null as string | null,
    device_requirement: null as string | null,
    power_requirement: null as string | null,
    languages: [] as string[],
    distribution_channels: [] as string[],
    target_groups: [] as string[],
    price_ngn: "",
    price_unit: "",
    objective: "pilot",
    budget_ngn: "",
    state_ids: [] as string[],
  });
  const set = <K extends keyof typeof f>(k: K) => (v: (typeof f)[K]) => setF((x) => ({ ...x, [k]: v }));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<MarketEntryResult | null>(null);
  const needs = vocab.sectors.find((s) => s.code === sector)?.needs ?? [];
  const stateOptions = Object.fromEntries(
    [...states].sort((a, b) => a.name.localeCompare(b.name)).map((s) => [String(s.id), s.name]),
  );
  const num = (v: string) => (v.trim() ? Number(v) : null);

  async function run(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setResult(
        await sendJson<MarketEntryResult>("/api/v1/market-entry", "POST", {
          sector,
          need: need || null,
          solution_id: solutionId ? Number(solutionId) : null,
          ...f,
          product_name: f.product_name || null,
          industry: f.industry || null,
          price_ngn: num(f.price_ngn),
          price_unit: f.price_unit || null,
          budget_ngn: num(f.budget_ngn),
          state_ids: f.state_ids.map(Number),
        }),
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The analysis failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <form onSubmit={run} className="space-y-6 rounded-lg border border-line bg-panel p-5">
        <FormSection title="Market">
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Sector" htmlFor="me-sector">
              <select id="me-sector" value={sector} onChange={(e) => { setSector(e.target.value); setNeed(""); }} className={inputClass}>
                {vocab.sectors.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}
              </select>
            </Field>
            <Field label="Need the product addresses" htmlFor="me-need">
              <select id="me-need" value={need} onChange={(e) => setNeed(e.target.value)} className={inputClass}>
                <option value="">Not specified</option>
                {needs.map((n) => <option key={n.code} value={n.code}>{n.name}</option>)}
              </select>
            </Field>
            <Field label="Expansion objective" htmlFor="me-objective">
              <select id="me-objective" value={f.objective} onChange={(e) => set("objective")(e.target.value)} className={inputClass}>
                {Object.entries(objectives).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </Field>
          </div>
          <CheckboxGroup legend="Preferred states (leave empty to compare all states)" name="states" options={stateOptions} value={f.state_ids} onChange={set("state_ids")} columns={3} />
        </FormSection>
        <FormSection title="Product" description="Pick a directory record, or describe the product. Leave unknowns empty.">
          {solutions.length > 0 && (
            <Field label="From the directory" htmlFor="me-solution">
              <select id="me-solution" value={solutionId} onChange={(e) => setSolutionId(e.target.value)} className={inputClass}>
                <option value="">Describe a product below instead</option>
                {solutions.map((s) => <option key={s.id} value={s.id}>{s.name} ({s.organisation_name})</option>)}
              </select>
            </Field>
          )}
          {!solutionId && (
            <>
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Product name" htmlFor="me-name"><input id="me-name" value={f.product_name} onChange={(e) => set("product_name")(e.target.value)} className={inputClass} /></Field>
                <Field label="Industry" htmlFor="me-industry"><input id="me-industry" value={f.industry} onChange={(e) => set("industry")(e.target.value)} className={inputClass} /></Field>
              </div>
              <div className="grid gap-3 sm:grid-cols-3">
                <UnknownSelect id="me-net" label="Internet needed" options={vocab.internet_requirements} value={f.internet_requirement} onChange={set("internet_requirement")} />
                <UnknownSelect id="me-dev" label="Device needed" options={vocab.device_requirements} value={f.device_requirement} onChange={set("device_requirement")} />
                <UnknownSelect id="me-pow" label="Electricity needed" options={vocab.power_requirements} value={f.power_requirement} onChange={set("power_requirement")} />
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label="Price (₦)" htmlFor="me-price"><input id="me-price" type="number" min={0} value={f.price_ngn} onChange={(e) => set("price_ngn")(e.target.value)} className={inputClass} /></Field>
                <Field label="Per" htmlFor="me-unit"><input id="me-unit" value={f.price_unit} onChange={(e) => set("price_unit")(e.target.value)} className={inputClass} /></Field>
              </div>
              <CheckboxGroup legend="Languages supported" name="langs" options={vocab.languages} value={f.languages} onChange={set("languages")} columns={3} />
              <CheckboxGroup legend="Distribution channels" name="channels" options={vocab.distribution_channels} value={f.distribution_channels} onChange={set("distribution_channels")} />
            </>
          )}
          <CheckboxGroup legend="Target beneficiaries" name="groups" options={vocab.beneficiary_groups} value={f.target_groups} onChange={set("target_groups")} columns={3} />
          <Field label="Budget (₦, optional)" htmlFor="me-budget" hint="Recorded with the analysis. No open cost data exists to compare it with.">
            <input id="me-budget" type="number" min={0} value={f.budget_ngn} onChange={(e) => set("budget_ngn")(e.target.value)} className={inputClass} />
          </Field>
        </FormSection>
        {error && <FormMessage tone="error">{error}</FormMessage>}
        <Button type="submit" busy={busy}>Analyse</Button>
      </form>
      {result && <Result r={result} />}
    </div>
  );
}

function Result({ r }: { r: MarketEntryResult }) {
  const scored = r.candidates.filter((c) => c.score !== null);
  return (
    <div className="space-y-4">
      <Panel title={`${r.objective}: ${r.product.name}`}>
        <p className="text-sm text-muted">
          {r.sector_name} · {r.needs.length ? r.needs.map((n) => n.name).join(", ") : "no specific need"} · requirements from {r.product.source}.
          Opportunity combines gap ({r.weights.gap * 100}%), fit with local conditions ({r.weights.fit * 100}%), reach ({r.weights.reach * 100}%) and fewer competitors ({r.weights.competition * 100}%), over the parts with data.
        </p>
        <div className="-mx-4 mt-3 overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <thead className="text-left text-xs text-muted">
              <tr>
                <th className="px-4 pb-2 font-normal">#</th>
                <th className="px-2 pb-2 font-normal">Area</th>
                <th className="px-2 pb-2 font-normal">Opportunity</th>
                <th className="px-2 pb-2 font-normal">Gap</th>
                <th className="px-2 pb-2 font-normal">Fit</th>
                <th className="px-2 pb-2 font-normal">Reach</th>
                <th className="px-2 pb-2 font-normal">Competitors</th>
                <th className="px-4 pb-2 font-normal">Population</th>
              </tr>
            </thead>
            <tbody>
              {r.candidates.slice(0, 15).map((c) => (
                <tr key={c.id} className="border-t border-line">
                  <td className="px-4 py-2 tabular-nums text-muted">{c.rank}</td>
                  <td className="px-2 py-2"><Link href={`/areas/${c.id}`} className="font-medium hover:text-brand">{c.name}</Link></td>
                  <td className="px-2 py-2 font-semibold tabular-nums">{c.score === null ? <span className="text-xs font-normal text-muted">need not evidenced</span> : Math.round(c.score)}</td>
                  {(["gap", "fit", "reach"] as const).map((k) => (
                    <td key={k} className="px-2 py-2 tabular-nums text-muted">{c.components[k] === null ? "unknown" : Math.round((c.components[k] as number) * 100)}</td>
                  ))}
                  <td className="px-2 py-2 tabular-nums text-muted">{c.competitors.length}</td>
                  <td className="px-4 py-2 tabular-nums text-muted">{c.population != null ? formatNumber(c.population) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {scored.length === 0 && (
          <p className="mt-3 text-sm text-gold-ink">
            No area has evidence of need in this sector, so none is ranked as an opportunity. Population and fit are shown for reference only.
          </p>
        )}
      </Panel>
      <div className="grid gap-4 lg:grid-cols-2">
        {r.sections.map((s) => (
          <Panel key={s.key} title={s.title}>
            <ul className="space-y-2.5">
              {s.items.map((it, i) => (
                <li key={i} className="text-sm">
                  <Badge tone={ITEM_KIND[it.kind].tone}>{ITEM_KIND[it.kind].label}</Badge> {it.text}
                  {it.evidence.length > 0 && <div className="mt-0.5 text-xs text-muted">{it.evidence.join(" · ")}</div>}
                </li>
              ))}
            </ul>
          </Panel>
        ))}
      </div>
      <p className="text-xs text-muted">
        Facts are read from the database with their source. Derived items are computed from facts. Recommendations apply stated rules to the evidence shown. Data gaps mark what is not known; nothing is estimated in their place. Market size, customer numbers, partnerships and costs are never invented.
      </p>
    </div>
  );
}
