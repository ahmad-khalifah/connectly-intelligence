"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import {
  Button,
  CheckboxGroup,
  Field,
  FormMessage,
  FormSection,
  inputClass,
  UnknownSelect,
} from "@/components/forms";
import { ApiError, type AreaSummary, clientApi, sendJson } from "@/lib/api";
import type { Coverage, Solution, Vocabularies } from "@/lib/directory";

type CoverageItem = Pick<Coverage, "area_id" | "name" | "level" | "kind"> & { state?: string };

const EMPTY = {
  name: "",
  sector: "",
  need_codes: [] as string[],
  summary: "",
  description: "",
  delivery_model: null as string | null,
  target_beneficiaries: "",
  beneficiary_groups: [] as string[],
  pricing_model: null as string | null,
  price_min_ngn: "",
  price_max_ngn: "",
  price_unit: "",
  pricing_notes: "",
  nationwide: false,
  distribution_channels: [] as string[],
  distribution_notes: "",
  internet_requirement: null as string | null,
  device_requirement: null as string | null,
  power_requirement: null as string | null,
  literacy_requirement: null as string | null,
  requirements_notes: "",
  languages: [] as string[],
  accessibility_features: [] as string[],
  accessibility_notes: "",
  partnership_types: [] as string[],
  partnership_notes: "",
  implementation_notes: "",
  evidence_of_impact: "",
  website: "",
  source_description: "",
  source_url: "",
};
type FormState = typeof EMPTY;

function fromSolution(s: Solution): FormState {
  const out = { ...EMPTY } as Record<string, unknown>;
  for (const k of Object.keys(EMPTY)) {
    const v = (s as unknown as Record<string, unknown>)[k];
    if (k === "price_min_ngn" || k === "price_max_ngn") out[k] = v == null ? "" : String(v);
    else if (v !== undefined) out[k] = v ?? (typeof EMPTY[k as keyof FormState] === "string" ? "" : null);
  }
  return out as FormState;
}

export function SolutionForm({
  vocab,
  states,
  organisationId,
  initial,
}: {
  vocab: Vocabularies;
  states: AreaSummary[];
  organisationId: number;
  initial?: Solution;
}) {
  const router = useRouter();
  const [f, setF] = useState<FormState>(initial ? fromSolution(initial) : EMPTY);
  const [coverage, setCoverage] = useState<CoverageItem[]>(initial?.coverage ?? []);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = <K extends keyof FormState>(k: K) => (v: FormState[K]) => setF((x) => ({ ...x, [k]: v }));
  const text = (k: keyof FormState) => ({
    value: f[k] as string,
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => set(k)(e.target.value as never),
  });

  const needOptions = useMemo(() => {
    const out: Record<string, string> = {};
    const sectors = [...vocab.sectors].sort((a, b) => (a.code === f.sector ? -1 : b.code === f.sector ? 1 : 0));
    for (const s of sectors) for (const n of s.needs) out[n.code] = s.code === f.sector ? n.name : `${n.name} (${s.name})`;
    return out;
  }, [vocab.sectors, f.sector]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const nn = (v: string) => (v.trim() === "" ? null : v.trim());
    const num = (v: string) => (v.trim() === "" ? null : Number(v));
    const body = {
      ...Object.fromEntries(Object.entries(f).map(([k, v]) => [k, typeof v === "string" ? nn(v) : v])),
      name: f.name.trim(),
      summary: f.summary.trim(),
      price_min_ngn: num(f.price_min_ngn),
      price_max_ngn: num(f.price_max_ngn),
      coverage: f.nationwide ? [] : coverage.map((c) => ({ area_id: c.area_id, kind: c.kind })),
    };
    setBusy(true);
    setError(null);
    try {
      const saved = initial
        ? await sendJson<Solution>(`/api/v1/solutions/${initial.id}`, "PUT", body)
        : await sendJson<Solution>(`/api/v1/organisations/${organisationId}/solutions`, "POST", body);
      router.push(`/directory/solutions/${saved.id}`);
      router.refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save.");
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-6">
      <p className="rounded-md border border-gold/40 bg-gold-soft px-3 py-2 text-sm text-gold-ink">
        Leave anything you do not know empty. Empty fields are shown as “not known” and lower the
        confidence of matches; they are never filled in automatically.
      </p>

      <FormSection title="Solution">
        <Field label="Name" htmlFor="name">
          <input id="name" required minLength={2} {...text("name")} className={inputClass} />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Main sector" htmlFor="sector">
            <select id="sector" required value={f.sector} onChange={(e) => set("sector")(e.target.value)} className={inputClass}>
              <option value="" disabled>
                Choose…
              </option>
              {vocab.sectors.map((s) => (
                <option key={s.code} value={s.code}>
                  {s.name}
                </option>
              ))}
            </select>
          </Field>
          <UnknownSelect id="delivery_model" label="Delivery model" options={vocab.delivery_models} value={f.delivery_model} onChange={set("delivery_model")} />
        </div>
        <Field label="Summary" htmlFor="summary" hint="One or two sentences, 10–400 characters">
          <textarea id="summary" required minLength={10} maxLength={400} rows={2} {...text("summary")} className={inputClass} />
        </Field>
        <Field label="Description" htmlFor="description">
          <textarea id="description" rows={5} {...text("description")} className={inputClass} />
        </Field>
        <Field label="Product website" htmlFor="website">
          <input id="website" type="url" placeholder="https://" {...text("website")} className={inputClass} />
        </Field>
      </FormSection>

      <FormSection title="Needs addressed" description="Matching uses these to decide relevance. Choose only needs the solution directly addresses.">
        {f.sector ? (
          <CheckboxGroup legend="Specific needs" name="need_codes" options={needOptions} value={f.need_codes} onChange={set("need_codes")} />
        ) : (
          <p className="text-sm text-muted">Choose a sector first.</p>
        )}
      </FormSection>

      <FormSection title="Beneficiaries">
        <CheckboxGroup legend="Who it is for" name="beneficiary_groups" options={vocab.beneficiary_groups} value={f.beneficiary_groups} onChange={set("beneficiary_groups")} columns={3} />
        <Field label="Target beneficiaries" htmlFor="target_beneficiaries" hint="In the provider's words">
          <textarea id="target_beneficiaries" rows={2} {...text("target_beneficiaries")} className={inputClass} />
        </Field>
      </FormSection>

      <FormSection title="Pricing" description="As published by the provider, in naira.">
        <UnknownSelect id="pricing_model" label="Pricing model" options={vocab.pricing_models} value={f.pricing_model} onChange={set("pricing_model")} />
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Lowest price (₦)" htmlFor="price_min_ngn">
            <input id="price_min_ngn" type="number" min={0} inputMode="numeric" {...text("price_min_ngn")} className={inputClass} />
          </Field>
          <Field label="Highest price (₦)" htmlFor="price_max_ngn">
            <input id="price_max_ngn" type="number" min={0} inputMode="numeric" {...text("price_max_ngn")} className={inputClass} />
          </Field>
          <Field label="Per" htmlFor="price_unit" hint="e.g. month, device, transaction">
            <input id="price_unit" {...text("price_unit")} className={inputClass} />
          </Field>
        </div>
        <Field label="Pricing notes" htmlFor="pricing_notes">
          <textarea id="pricing_notes" rows={2} {...text("pricing_notes")} className={inputClass} />
        </Field>
      </FormSection>

      <FormSection title="Where it is available" description="Operating areas count as available in matching. Expansion interests are shown separately.">
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={f.nationwide} onChange={(e) => set("nationwide")(e.target.checked)} className="h-4 w-4 accent-[var(--color-brand)]" />
          Available in every state
        </label>
        {!f.nationwide && <CoverageEditor states={states} value={coverage} onChange={setCoverage} />}
      </FormSection>

      <FormSection title="What users need" description="Compared with each community's connectivity, power and devices in matching.">
        <div className="grid gap-4 sm:grid-cols-2">
          <UnknownSelect id="internet_requirement" label="Internet" options={vocab.internet_requirements} value={f.internet_requirement} onChange={set("internet_requirement")} />
          <UnknownSelect id="device_requirement" label="Device" options={vocab.device_requirements} value={f.device_requirement} onChange={set("device_requirement")} />
          <UnknownSelect id="power_requirement" label="Electricity" options={vocab.power_requirements} value={f.power_requirement} onChange={set("power_requirement")} />
          <UnknownSelect id="literacy_requirement" label="Literacy" options={vocab.literacy_requirements} value={f.literacy_requirement} onChange={set("literacy_requirement")} />
        </div>
        <Field label="Notes" htmlFor="requirements_notes">
          <textarea id="requirements_notes" rows={2} {...text("requirements_notes")} className={inputClass} />
        </Field>
      </FormSection>

      <FormSection title="Languages and accessibility">
        <CheckboxGroup legend="Languages supported" name="languages" options={vocab.languages} value={f.languages} onChange={set("languages")} columns={3} />
        <CheckboxGroup legend="Accessibility features" name="accessibility_features" options={vocab.accessibility_features} value={f.accessibility_features} onChange={set("accessibility_features")} />
        <Field label="Accessibility notes" htmlFor="accessibility_notes">
          <textarea id="accessibility_notes" rows={2} {...text("accessibility_notes")} className={inputClass} />
        </Field>
      </FormSection>

      <FormSection title="Distribution and partnerships">
        <CheckboxGroup legend="How it reaches users" name="distribution_channels" options={vocab.distribution_channels} value={f.distribution_channels} onChange={set("distribution_channels")} />
        <Field label="Distribution requirements" htmlFor="distribution_notes">
          <textarea id="distribution_notes" rows={2} {...text("distribution_notes")} className={inputClass} />
        </Field>
        <CheckboxGroup legend="Partnerships sought" name="partnership_types" options={vocab.partnership_types} value={f.partnership_types} onChange={set("partnership_types")} />
        <Field label="Partnership notes" htmlFor="partnership_notes">
          <textarea id="partnership_notes" rows={2} {...text("partnership_notes")} className={inputClass} />
        </Field>
      </FormSection>

      <FormSection title="Implementation and evidence">
        <Field label="Implementation requirements" htmlFor="implementation_notes" hint="Staff, set-up time, approvals or equipment a deployment needs">
          <textarea id="implementation_notes" rows={3} {...text("implementation_notes")} className={inputClass} />
        </Field>
        <Field label="Evidence of impact" htmlFor="evidence_of_impact" hint="Only results that have been reported, with where they were reported">
          <textarea id="evidence_of_impact" rows={3} {...text("evidence_of_impact")} className={inputClass} />
        </Field>
      </FormSection>

      <FormSection title="Source" description="Where this information comes from. Shown with the record.">
        <Field label="Source" htmlFor="source_description">
          <input id="source_description" required minLength={5} {...text("source_description")} className={inputClass} />
        </Field>
        <Field label="Source link" htmlFor="source_url">
          <input id="source_url" type="url" placeholder="https://" {...text("source_url")} className={inputClass} />
        </Field>
      </FormSection>

      {error && <FormMessage tone="error">{error}</FormMessage>}
      <div className="flex gap-3">
        <Button type="submit" busy={busy}>
          {initial ? "Save changes" : "Save as draft"}
        </Button>
        <Link href={initial ? `/directory/solutions/${initial.id}` : `/directory/organisations/${organisationId}`} className="rounded-md px-4 py-2 text-sm text-muted hover:text-ink">
          Cancel
        </Link>
      </div>
    </form>
  );
}

function CoverageEditor({
  states,
  value,
  onChange,
}: {
  states: AreaSummary[];
  value: CoverageItem[];
  onChange: (v: CoverageItem[]) => void;
}) {
  const [stateId, setStateId] = useState("");
  const [lgas, setLgas] = useState<AreaSummary[]>([]);
  const [lgaId, setLgaId] = useState("");
  const [kind, setKind] = useState<CoverageItem["kind"]>("operating");

  async function pickState(id: string) {
    setStateId(id);
    setLgaId("");
    setLgas(id ? await clientApi<AreaSummary[]>(`/api/v1/areas/${id}/children`) : []);
  }

  function add() {
    const st = states.find((s) => String(s.id) === stateId);
    if (!st) return;
    const lga = lgas.find((l) => String(l.id) === lgaId);
    const area = lga ?? st;
    if (value.some((v) => v.area_id === area.id && v.kind === kind)) return;
    onChange([...value, { area_id: area.id, name: area.name, level: area.level, kind, state: lga ? st.name : undefined }]);
  }

  return (
    <div className="space-y-3">
      <div className="grid gap-2 sm:grid-cols-[1fr_1fr_11rem_auto] sm:items-end">
        <Field label="State" htmlFor="cov-state">
          <select id="cov-state" value={stateId} onChange={(e) => pickState(e.target.value)} className={inputClass}>
            <option value="">Choose…</option>
            {states.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="LGA (optional)" htmlFor="cov-lga">
          <select id="cov-lga" value={lgaId} disabled={!stateId} onChange={(e) => setLgaId(e.target.value)} className={inputClass}>
            <option value="">Whole state</option>
            {lgas.map((l) => (
              <option key={l.id} value={l.id}>
                {l.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Type" htmlFor="cov-kind">
          <select id="cov-kind" value={kind} onChange={(e) => setKind(e.target.value as CoverageItem["kind"])} className={inputClass}>
            <option value="operating">Operates there</option>
            <option value="expansion_interest">Wants to expand there</option>
          </select>
        </Field>
        <Button type="button" variant="secondary" onClick={add} disabled={!stateId}>
          Add
        </Button>
      </div>
      {value.length === 0 ? (
        <p className="text-xs text-muted">No areas added. Coverage will show as “not stated”.</p>
      ) : (
        <ul className="flex flex-wrap gap-2">
          {value.map((c) => (
            <li key={`${c.area_id}-${c.kind}`} className={`flex items-center gap-2 rounded-full border px-3 py-1 text-xs ${c.kind === "operating" ? "border-brand/30 bg-brand-soft text-brand" : "border-gold/40 bg-gold-soft text-gold-ink"}`}>
              {c.name}
              {c.level !== "state" && <span className="opacity-70">({c.level.toUpperCase()})</span>}
              {c.kind === "expansion_interest" && <span className="opacity-70">· expansion</span>}
              <button type="button" aria-label={`Remove ${c.name}`} onClick={() => onChange(value.filter((v) => v !== c))} className="ml-1 font-semibold">
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
