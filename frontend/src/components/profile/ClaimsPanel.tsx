"use client";

import { useState } from "react";

import { Button, Field, FormMessage, inputClass } from "@/components/forms";
import { Badge } from "@/components/ui";
import { ApiError, type Claim, clientApi, sendJson } from "@/lib/api";

import { ValueBadges } from "./Values";

const CLAIM_VALUE_TYPES: Record<string, string> = {
  measured: "Observed or reported directly",
  estimated: "Estimate",
  derived: "Worked out from other sources",
  assumed: "Assumption (not checked)",
};

interface Props {
  subjectType: "admin_area" | "settlement";
  subjectId: number;
  initial: Claim[];
  attributes: Record<string, string>;
  languages: Record<string, string>;
  user: { id: number; role: string };
}

interface HistoryEntry {
  created_at: string;
  actor: string;
  action: string;
  summary: string | null;
}

export function ClaimsPanel({ subjectType, subjectId, initial, attributes, languages, user }: Props) {
  const [claims, setClaims] = useState(initial);
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<Claim | null>(null);
  const canWrite = user.role === "admin" || user.role === "researcher";

  async function reload() {
    setClaims(await clientApi<Claim[]>(`/api/v1/claims?subject_type=${subjectType}&subject_id=${subjectId}`));
  }

  return (
    <div className="space-y-4">
      {claims.length === 0 && !adding && (
        <p className="text-sm text-muted">
          No community information recorded yet. Economic activities, languages, market days and
          local organisations are not in any open dataset; they are added here by researchers
          with their source, and reviewed by a second person.
        </p>
      )}
      <ul className="divide-y divide-line">
        {claims.map((c) =>
          editing?.id === c.id ? (
            <li key={c.id} className="py-3">
              <ClaimForm
                attributes={attributes}
                languages={languages}
                initial={c}
                onCancel={() => setEditing(null)}
                onSave={async (body) => {
                  await sendJson(`/api/v1/claims/${c.id}`, "PATCH", body);
                  setEditing(null);
                  await reload();
                }}
              />
            </li>
          ) : (
            <ClaimItem key={c.id} c={c} user={user} languages={languages} onChanged={reload} onEdit={() => setEditing(c)} />
          ),
        )}
      </ul>
      {canWrite &&
        (adding ? (
          <ClaimForm
            attributes={attributes}
            languages={languages}
            onCancel={() => setAdding(false)}
            onSave={async (body) => {
              await sendJson("/api/v1/claims", "POST", { ...body, subject_type: subjectType, subject_id: subjectId });
              setAdding(false);
              await reload();
            }}
          />
        ) : (
          <Button variant="secondary" onClick={() => setAdding(true)}>
            Add information
          </Button>
        ))}
    </div>
  );
}

function ClaimItem({
  c,
  user,
  languages,
  onChanged,
  onEdit,
}: {
  c: Claim;
  user: Props["user"];
  languages: Record<string, string>;
  onChanged: () => Promise<void>;
  onEdit: () => void;
}) {
  const [mode, setMode] = useState<null | "review" | "retire">(null);
  const [note, setNote] = useState("");
  const [status, setStatus] = useState("source_verified");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState<HistoryEntry[] | null>(null);
  const isAuthor = c.created_by_id === user.id;
  const canReview = (user.role === "admin" || user.role === "researcher") && !isAuthor;
  const canChange = isAuthor || user.role === "admin";

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      if (mode === "review") await sendJson(`/api/v1/claims/${c.id}/review`, "POST", { status, note });
      else await sendJson(`/api/v1/claims/${c.id}/retire`, "POST", { note });
      setMode(null);
      setNote("");
      await onChanged();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="py-3 first:pt-0">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-medium uppercase tracking-wide text-muted">{c.attribute_label}</span>
        <ValueBadges v={c} />
      </div>
      <p className="mt-1 whitespace-pre-line text-sm">{c.value_text}</p>
      {c.value_codes && c.value_codes.length > 0 && (
        <div className="mt-1 flex flex-wrap gap-1">
          {c.value_codes.map((code) => (
            <Badge key={code}>{languages[code] ?? code}</Badge>
          ))}
        </div>
      )}
      <p className="mt-1 text-xs text-muted">
        Source: {c.source_description}
        {c.source_url && (
          <>
            {" "}
            · <a href={c.source_url} className="text-brand hover:underline" target="_blank" rel="noopener noreferrer">link</a>
          </>
        )}
        {c.observed_on && <> · observed {c.observed_on}</>}
        {c.created_by && <> · entered by {c.created_by}</>}
        {c.verified_by && <> · reviewed by {c.verified_by}</>}
      </p>
      {c.verification_note && <p className="mt-0.5 text-xs text-muted">Review note: {c.verification_note}</p>}
      <div className="mt-2 flex flex-wrap gap-3 text-xs">
        {canReview && <button className="text-brand hover:underline" onClick={() => setMode("review")}>Review</button>}
        {canChange && <button className="text-brand hover:underline" onClick={onEdit}>Edit</button>}
        {canChange && <button className="text-bad hover:underline" onClick={() => setMode("retire")}>Retire</button>}
        <button
          className="text-muted hover:text-ink"
          onClick={async () => setHistory(history ? null : await clientApi<HistoryEntry[]>(`/api/v1/claims/${c.id}/history`))}
        >
          {history ? "Hide history" : "History"}
        </button>
      </div>
      {history && (
        <ol className="mt-2 space-y-0.5 border-l-2 border-gold/50 pl-3 text-xs text-muted">
          {history.map((h, i) => (
            <li key={i}>
              {new Date(h.created_at).toLocaleString("en-GB")} · {h.actor} · {h.action}
              {h.summary ? ` · ${h.summary}` : ""}
            </li>
          ))}
        </ol>
      )}
      {mode && (
        <form
          className="mt-3 space-y-2 rounded-md border border-line bg-paper p-3"
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          {mode === "review" && (
            <Field label="Result" htmlFor={`status-${c.id}`}>
              <select id={`status-${c.id}`} value={status} onChange={(e) => setStatus(e.target.value)} className={inputClass}>
                <option value="source_verified">Checked against the stated source</option>
                <option value="field_verified">Confirmed in the field</option>
                <option value="disputed">Disputed</option>
              </select>
            </Field>
          )}
          <Field label={mode === "review" ? "What you checked, and how" : "Why retire it"} htmlFor={`note-${c.id}`}>
            <textarea id={`note-${c.id}`} required minLength={5} rows={2} value={note} onChange={(e) => setNote(e.target.value)} className={inputClass} />
          </Field>
          {error && <FormMessage tone="error">{error}</FormMessage>}
          <div className="flex gap-2">
            <Button type="submit" busy={busy}>
              {mode === "review" ? "Save review" : "Retire"}
            </Button>
            <Button type="button" variant="ghost" onClick={() => setMode(null)}>
              Cancel
            </Button>
          </div>
        </form>
      )}
    </li>
  );
}

function ClaimForm({
  attributes,
  languages,
  initial,
  onSave,
  onCancel,
}: {
  attributes: Record<string, string>;
  languages: Record<string, string>;
  initial?: Claim;
  onSave: (body: Record<string, unknown>) => Promise<void>;
  onCancel: () => void;
}) {
  const [attribute, setAttribute] = useState(initial?.attribute ?? "");
  const [codes, setCodes] = useState<string[]>(initial?.value_codes ?? []);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const s = (k: string) => String(f.get(k) ?? "").trim() || null;
    const body: Record<string, unknown> = {
      value_text: s("value_text"),
      value_type: s("value_type"),
      source_description: s("source_description"),
      source_url: s("source_url"),
      observed_on: s("observed_on"),
      value_codes: attribute === "languages" ? codes : null,
    };
    if (!initial) body.attribute = attribute;
    setBusy(true);
    setError(null);
    try {
      await onSave(body);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save.");
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="space-y-3 rounded-md border border-line bg-paper p-4">
      <p className="text-xs text-muted">
        Record facts about the place, not about individual residents. Do not enter names, phone
        numbers or other personal details.
      </p>
      {!initial && (
        <Field label="What this is about" htmlFor="attribute">
          <select id="attribute" required value={attribute} onChange={(e) => setAttribute(e.target.value)} className={inputClass}>
            <option value="" disabled>
              Choose…
            </option>
            {Object.entries(attributes).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </Field>
      )}
      {attribute === "languages" && (
        <fieldset>
          <legend className="mb-1 text-sm font-medium">Languages</legend>
          <div className="grid gap-1 sm:grid-cols-3">
            {Object.entries(languages).map(([code, name]) => (
              <label key={code} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={codes.includes(code)}
                  onChange={(e) => setCodes(e.target.checked ? [...codes, code] : codes.filter((c) => c !== code))}
                  className="h-4 w-4 accent-[var(--color-brand)]"
                />
                {name}
              </label>
            ))}
          </div>
        </fieldset>
      )}
      <Field label="Information" htmlFor="value_text">
        <textarea id="value_text" name="value_text" required minLength={2} rows={3} defaultValue={initial?.value_text} className={inputClass} />
      </Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="How it is known" htmlFor="value_type">
          <select id="value_type" name="value_type" required defaultValue={initial?.value_type ?? "measured"} className={inputClass}>
            {Object.entries(CLAIM_VALUE_TYPES).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </Field>
        <Field label="When observed" htmlFor="observed_on" hint="Date or period, e.g. 2026-10">
          <input id="observed_on" name="observed_on" maxLength={32} defaultValue={initial?.observed_on ?? ""} className={inputClass} />
        </Field>
      </div>
      <Field label="Source" htmlFor="source_description" hint="Who or what this comes from, e.g. field visit, LGA office report">
        <input id="source_description" name="source_description" required minLength={5} defaultValue={initial?.source_description} className={inputClass} />
      </Field>
      <Field label="Source link (optional)" htmlFor="source_url">
        <input id="source_url" name="source_url" type="url" placeholder="https://" defaultValue={initial?.source_url ?? ""} className={inputClass} />
      </Field>
      {initial && <p className="text-xs text-gold-ink">Saving sends this information back for review.</p>}
      {error && <FormMessage tone="error">{error}</FormMessage>}
      <div className="flex gap-2">
        <Button type="submit" busy={busy}>
          Save
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </form>
  );
}

