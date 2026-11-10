"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button, Field, FormMessage, FormSection, inputClass } from "@/components/forms";
import { ApiError, type AreaSummary, sendJson } from "@/lib/api";
import type { Organisation, Vocabularies } from "@/lib/directory";

export function OrganisationForm({
  vocab,
  states,
  initial,
}: {
  vocab: Vocabularies;
  states: AreaSummary[];
  initial?: Organisation;
}) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [country, setCountry] = useState(initial?.headquarters_country ?? "NG");

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const s = (k: string) => (String(f.get(k) ?? "").trim() || null);
    const body = {
      name: s("name"),
      org_type: s("org_type"),
      industry: s("industry"),
      website: s("website"),
      description: s("description"),
      headquarters: s("headquarters"),
      headquarters_country: (s("headquarters_country") ?? "NG").toUpperCase(),
      headquarters_state_id: country.toUpperCase() === "NG" && s("headquarters_state_id") ? Number(s("headquarters_state_id")) : null,
      source_description: s("source_description"),
      source_url: s("source_url"),
    };
    setBusy(true);
    setError(null);
    try {
      const org = initial
        ? await sendJson<Organisation>(`/api/v1/organisations/${initial.id}`, "PUT", body)
        : await sendJson<Organisation>("/api/v1/organisations", "POST", body);
      router.push(`/directory/organisations/${org.id}`);
      router.refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save.");
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-6">
      <FormSection title="Organisation">
        <Field label="Name" htmlFor="org-name">
          <input id="org-name" name="name" required minLength={2} defaultValue={initial?.name} className={inputClass} />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Type" htmlFor="org-org_type">
            <select id="org-org_type" name="org_type" required defaultValue={initial?.org_type ?? ""} className={inputClass}>
              <option value="" disabled>
                Choose…
              </option>
              {Object.entries(vocab.org_types).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Industry" htmlFor="org-industry" hint="As the organisation describes itself">
            <input id="org-industry" name="industry" defaultValue={initial?.industry ?? ""} className={inputClass} />
          </Field>
        </div>
        <Field label="Website" htmlFor="org-website">
          <input id="org-website" name="website" type="url" placeholder="https://" defaultValue={initial?.website ?? ""} className={inputClass} />
        </Field>
        <Field label="Description" htmlFor="org-description">
          <textarea id="org-description" name="description" rows={4} defaultValue={initial?.description ?? ""} className={inputClass} />
        </Field>
      </FormSection>
      <FormSection title="Headquarters">
        <div className="grid gap-4 sm:grid-cols-[1fr_8rem]">
          <Field label="Town or city" htmlFor="org-headquarters">
            <input id="org-headquarters" name="headquarters" defaultValue={initial?.headquarters ?? ""} className={inputClass} />
          </Field>
          <Field label="Country" htmlFor="org-headquarters_country" hint="Two-letter code">
            <input
              id="org-headquarters_country"
              name="headquarters_country"
              required
              maxLength={2}
              minLength={2}
              value={country}
              onChange={(e) => setCountry(e.target.value.toUpperCase())}
              className={`${inputClass} uppercase`}
            />
          </Field>
        </div>
        {country === "NG" && (
          <Field label="State" htmlFor="org-headquarters_state_id">
            <select id="org-headquarters_state_id" name="headquarters_state_id" defaultValue={initial?.headquarters_state_id ?? ""} className={inputClass}>
              <option value="">Not stated</option>
              {states.map((st) => (
                <option key={st.id} value={st.id}>
                  {st.name}
                </option>
              ))}
            </select>
          </Field>
        )}
      </FormSection>
      <FormSection title="Source" description="Where this information comes from. It is shown with the record.">
        <Field label="Source" htmlFor="org-source_description" hint="For example: company website, retrieved 10 November 2026">
          <input id="org-source_description" name="source_description" required minLength={5} defaultValue={initial?.source_description ?? ""} className={inputClass} />
        </Field>
        <Field label="Source link" htmlFor="org-source_url">
          <input id="org-source_url" name="source_url" type="url" placeholder="https://" defaultValue={initial?.source_url ?? ""} className={inputClass} />
        </Field>
      </FormSection>
      {error && <FormMessage tone="error">{error}</FormMessage>}
      <div className="flex gap-3">
        <Button type="submit" busy={busy}>
          {initial ? "Save changes" : "Create organisation"}
        </Button>
        <Link href={initial ? `/directory/organisations/${initial.id}` : "/directory"} className="rounded-md px-4 py-2 text-sm text-muted hover:text-ink">
          Cancel
        </Link>
      </div>
    </form>
  );
}
