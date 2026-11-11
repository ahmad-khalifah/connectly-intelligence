"use client";

import { useCallback, useEffect, useState } from "react";

import { Button, Field, FormMessage, inputClass } from "@/components/forms";
import { AreaPicker } from "@/components/matching/AreaPicker";
import { Badge, Panel } from "@/components/ui";
import {
  ApiError,
  type AreaSummary,
  clientApi,
  FINDING_KIND,
  type FindingStatus,
  type LiveResearch,
  type ResearchFinding,
  type ResearchStatus,
  type ResearchZone,
  sendJson,
  type SourceAnalysis,
} from "@/lib/api";

type Opt = { code: string; name: string };

const STATUS_TONE: Record<FindingStatus, "neutral" | "good" | "bad" | "warn"> = {
  unverified: "warn",
  source_verified: "good",
  field_verified: "good",
  disputed: "bad",
  retired: "neutral",
};

const message = (err: unknown, fallback: string) => (err instanceof ApiError && err.message ? err.message : fallback);

export function Research({
  status,
  zones,
  sectors,
  canResearch,
}: {
  status: ResearchStatus;
  zones: ResearchZone[];
  sectors: Opt[];
  canResearch: boolean;
}) {
  const [usage, setUsage] = useState(status.usage);
  const [refresh, setRefresh] = useState(0);
  const onUsed = useCallback(async () => {
    try {
      setUsage((await clientApi<ResearchStatus>("/api/v1/research/status")).usage);
    } catch {
      /* the counts are informative only */
    }
  }, []);
  return (
    <div className="space-y-6">
      <StatusStrip status={status} usage={usage} />
      {canResearch && status.configured && (
        <>
          <LivePanel zones={zones} sectors={sectors} onUsed={onUsed} />
          <SourcePanel sectors={sectors} onUsed={onUsed} onStored={() => setRefresh((n) => n + 1)} />
        </>
      )}
      {!canResearch && (
        <p className="text-sm text-muted">Web research and source analysis are open to researchers and administrators. You can read the findings below.</p>
      )}
      <FindingsPanel sectors={sectors} canReview={canResearch} refresh={refresh} />
    </div>
  );
}

function StatusStrip({ status, usage }: { status: ResearchStatus; usage: ResearchStatus["usage"] }) {
  if (!status.configured) {
    return (
      <div className="rounded-lg border border-line bg-panel p-4 text-sm" role="status">
        <div className="font-semibold">Research is off</div>
        <p className="mt-1 text-muted">{status.message}</p>
      </div>
    );
  }
  const resets = new Date(usage.resets_at).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });
  return (
    <div className="rounded-lg border border-line bg-panel p-4 text-sm" role="status">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="brand">Gemini free tier</Badge>
        <span className="text-muted">
          Web research {usage.searches}/{usage.search_limit} today · other AI requests {usage.requests}/{usage.request_limit} · resets {resets}
        </span>
        {usage.blocked_until && <Badge tone="bad">Paused by Google&apos;s limit until {new Date(usage.blocked_until).toLocaleTimeString("en-GB")}</Badge>}
      </div>
      <p className="mt-2 text-xs text-muted">{status.notice}</p>
    </div>
  );
}

// ---------------------------------------------------------------------- live research

function LivePanel({ zones, sectors, onUsed }: { zones: ResearchZone[]; sectors: Opt[]; onUsed: () => void }) {
  const [states, setStates] = useState<AreaSummary[]>([]);
  const [question, setQuestion] = useState("");
  const [scope, setScope] = useState("");
  const [sector, setSector] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [answer, setAnswer] = useState<LiveResearch | null>(null);

  useEffect(() => {
    clientApi<AreaSummary[]>("/api/v1/areas?level=state").then(setStates, () => setStates([]));
  }, []);

  async function run(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setAnswer(null);
    const [kind, value] = scope.split(":");
    try {
      setAnswer(
        await sendJson<LiveResearch>("/api/v1/research/live", "POST", {
          question: question.trim(),
          sector: sector || null,
          zone: kind === "zone" ? value : null,
          state_ids: kind === "state" ? [Number(value)] : null,
        }),
      );
    } catch (err) {
      setError(message(err, "The research request failed."));
    } finally {
      setBusy(false);
      onUsed();
    }
  }

  return (
    <Panel title="Live web research">
      <form onSubmit={run} className="space-y-4">
        <Field label="Question" htmlFor="r-q" hint="Do not include names, phone numbers or other personal details">
          <textarea
            id="r-q"
            required
            minLength={10}
            maxLength={1000}
            rows={2}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Identify communities in Northern Nigeria with limited access to digital healthcare."
            className={inputClass}
          />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Where" htmlFor="r-scope">
            <select id="r-scope" value={scope} onChange={(e) => setScope(e.target.value)} className={inputClass}>
              <option value="">All of Nigeria</option>
              <optgroup label="Regions and zones">
                {zones.map((z) => (
                  <option key={z.code} value={`zone:${z.code}`}>{z.name}</option>
                ))}
              </optgroup>
              <optgroup label="States">
                {states.map((s) => (
                  <option key={s.id} value={`state:${s.id}`}>{s.name}</option>
                ))}
              </optgroup>
            </select>
          </Field>
          <Field label="Sector" htmlFor="r-sector">
            <select id="r-sector" value={sector} onChange={(e) => setSector(e.target.value)} className={inputClass}>
              <option value="">Any sector</option>
              {sectors.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}
            </select>
          </Field>
        </div>
        {error && <FormMessage tone="error">{error}</FormMessage>}
        <Button type="submit" busy={busy}>Research</Button>
      </form>
      {answer && <LiveAnswer a={answer} />}
    </Panel>
  );
}

/** Insert numbered source markers where Google says each passage is supported. */
function annotate(a: LiveResearch): React.ReactNode[] {
  const marks = [...a.supports].filter((s) => s.sources.length).sort((x, y) => x.end - y.end);
  const out: React.ReactNode[] = [];
  let at = 0;
  marks.forEach((s, i) => {
    if (s.end < at) return;
    out.push(a.text.slice(at, s.end));
    out.push(
      <sup key={`m${i}`} className="ml-0.5 text-xs">
        {s.sources.map((n) => (
          <a key={n} href={`#src-${n}`} className="mr-0.5 text-brand hover:underline">[{n + 1}]</a>
        ))}
      </sup>,
    );
    at = s.end;
  });
  out.push(a.text.slice(at));
  return out;
}

function LiveAnswer({ a }: { a: LiveResearch }) {
  return (
    <div className="mt-6 space-y-4 border-t border-line pt-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="bad">AI-generated</Badge>
        <Badge tone="warn">Unverified</Badge>
        <Badge>Not stored</Badge>
        <span className="text-xs text-muted">{a.model} with Google Search · {a.scope.label}</span>
      </div>
      {a.scope.missing_states.length > 0 && (
        <p className="text-xs text-muted">Not loaded in the platform yet, but included by name: {a.scope.missing_states.join(", ")}.</p>
      )}
      <div className="whitespace-pre-line text-sm leading-relaxed">{annotate(a)}</div>
      <div>
        <h3 className="text-sm font-semibold">Sources found by Google Search</h3>
        {a.sources.length ? (
          <ol className="mt-1 space-y-1 text-sm">
            {a.sources.map((s) => (
              <li key={s.index} id={`src-${s.index}`} className="scroll-mt-24">
                <span className="mr-1 text-muted">[{s.index + 1}]</span>
                {s.uri ? (
                  <a href={s.uri} target="_blank" rel="noopener noreferrer" className="text-brand hover:underline">{s.title ?? "Source"}</a>
                ) : (
                  s.title
                )}
              </li>
            ))}
          </ol>
        ) : (
          <p className="text-sm text-muted">No sources were returned. Treat the answer as unsupported.</p>
        )}
        <p className="mt-1 text-xs text-muted">To keep evidence from a source, open it and paste the page&apos;s own address into &ldquo;Analyse a source&rdquo;.</p>
      </div>
      {a.search_entry_point_html && <SearchSuggestions html={a.search_entry_point_html} />}
      <ul className="list-disc space-y-0.5 pl-5 text-xs text-muted">
        {a.limitations.map((l) => <li key={l}>{l}</li>)}
      </ul>
      <p className="text-xs text-muted">{a.notice}</p>
    </div>
  );
}

/** Google's Search Suggestions, shown as provided, isolated in a sandboxed frame. */
function SearchSuggestions({ html }: { html: string }) {
  const [height, setHeight] = useState(64);
  return (
    <div>
      <h3 className="mb-1 text-xs font-semibold text-muted">Google Search Suggestions</h3>
      <iframe
        title="Google Search Suggestions"
        sandbox="allow-popups allow-popups-to-escape-sandbox"
        srcDoc={`<!doctype html><html><head><meta charset="utf-8"><base target="_blank"></head><body style="margin:0">${html}</body></html>`}
        className="w-full rounded border border-line"
        style={{ height }}
        onLoad={(e) => {
          try {
            const h = e.currentTarget.contentDocument?.body.scrollHeight;
            if (h) setHeight(h + 8);
          } catch {
            /* the sandbox may hide the size; keep the default */
          }
        }}
      />
    </div>
  );
}

// ---------------------------------------------------------------------- source analysis

function SourcePanel({ sectors, onUsed, onStored }: { sectors: Opt[]; onUsed: () => void; onStored: () => void }) {
  const [url, setUrl] = useState("");
  const [sector, setSector] = useState("");
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SourceAnalysis | null>(null);

  async function run(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const r = await sendJson<SourceAnalysis>("/api/v1/research/sources", "POST", {
        url: url.trim(),
        sector: sector || null,
        question: question.trim() || null,
      });
      setResult(r);
      if (r.findings.length) onStored();
    } catch (err) {
      setError(message(err, "The source could not be analysed."));
    } finally {
      setBusy(false);
      onUsed();
    }
  }

  return (
    <Panel title="Analyse a source">
      <form onSubmit={run} className="space-y-4">
        <Field label="Web address of a public page or PDF" htmlFor="s-url" hint="Use the page's own address, not a Google redirect link">
          <input id="s-url" type="url" required value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://" className={inputClass} />
        </Field>
        <div className="grid gap-3 sm:grid-cols-[1fr_2fr]">
          <Field label="Sector" htmlFor="s-sector">
            <select id="s-sector" value={sector} onChange={(e) => setSector(e.target.value)} className={inputClass}>
              <option value="">Any sector</option>
              {sectors.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}
            </select>
          </Field>
          <Field label="Focus (optional)" htmlFor="s-q">
            <input id="s-q" maxLength={500} value={question} onChange={(e) => setQuestion(e.target.value)} className={inputClass} />
          </Field>
        </div>
        {error && <FormMessage tone="error">{error}</FormMessage>}
        <Button type="submit" busy={busy}>Fetch and extract findings</Button>
      </form>
      {result && (
        <div className="mt-6 space-y-3 border-t border-line pt-4 text-sm">
          <SourceLine s={result.source} />
          <p>
            {result.findings.length} finding{result.findings.length === 1 ? "" : "s"} stored, {result.rejected.length} rejected
            {result.from_cache ? " (extraction reused from the cache; Gemini was not called)" : ""}.
            {result.truncated ? " Only the first part of a long document was read." : ""}
          </p>
          <ul className="space-y-3">
            {result.findings.map((f) => <FindingCard key={f.id} f={f} />)}
          </ul>
          {result.rejected.length > 0 && (
            <details>
              <summary className="cursor-pointer text-muted">Rejected by the checks</summary>
              <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs text-muted">
                {result.rejected.map((r, i) => <li key={i}>{r.statement || "(no statement)"} — {r.reason}</li>)}
              </ul>
            </details>
          )}
          <p className="text-xs text-muted">{result.notice}</p>
        </div>
      )}
    </Panel>
  );
}

// ---------------------------------------------------------------------- findings

function SourceLine({ s }: { s: ResearchFinding["source"] }) {
  return (
    <div className="text-xs text-muted">
      <a href={s.url} target="_blank" rel="noopener noreferrer" className="font-medium text-brand hover:underline">
        {s.title ?? s.url}
      </a>
      {s.publisher && <> · {s.publisher}</>}
      {" · "}published {s.published_on ?? "date unknown"}
      {s.published_basis && <> ({s.published_basis})</>} · retrieved {s.retrieved_at.slice(0, 10)}
    </div>
  );
}

function FindingCard({ f, children }: { f: ResearchFinding; children?: React.ReactNode }) {
  return (
    <li className="rounded-lg border border-line p-3">
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge tone={STATUS_TONE[f.verification_status]}>{f.verification_status.replace("_", " ")}</Badge>
        <Badge tone="gold">{FINDING_KIND[f.kind]}</Badge>
        {f.sector && <Badge>{f.sector}</Badge>}
        {f.period && <span className="text-xs text-muted">{f.period}</span>}
      </div>
      <p className="mt-2 text-sm">{f.statement}</p>
      <blockquote className="mt-2 border-l-2 border-gold pl-3 text-sm italic text-muted">&ldquo;{f.quote}&rdquo;</blockquote>
      <div className="mt-2 text-xs text-muted">
        About: {f.areas.map((a) => a.name).join(", ") || "—"}
        {f.places.length > 0 && <> · as named in the source: {f.places.join(", ")}</>}
      </div>
      <div className="mt-1"><SourceLine s={f.source} /></div>
      <div className="mt-1 text-xs text-muted">
        Statement written by {f.extracted_by.replace("gemini:", "Gemini (AI), ")}; the quote is the source&apos;s own words.
        {f.verification_note && <> Review: {f.verification_note}</>}
      </div>
      {children}
    </li>
  );
}

function FindingsPanel({ sectors, canReview, refresh }: { sectors: Opt[]; canReview: boolean; refresh: number }) {
  const [areaId, setAreaId] = useState<number | null>(null);
  const [sector, setSector] = useState("");
  const [status, setStatus] = useState("");
  const [items, setItems] = useState<ResearchFinding[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [tick, setTick] = useState(0);
  const query = new URLSearchParams(
    Object.entries({ area_id: areaId ? String(areaId) : "", sector, status }).filter(([, v]) => v),
  ).toString();

  useEffect(() => {
    let alive = true;
    clientApi<ResearchFinding[]>(`/api/v1/research/findings?${query}`).then(
      (r) => {
        if (!alive) return;
        setItems(r);
        setError(null);
      },
      (err) => alive && setError(message(err, "Findings could not be loaded.")),
    );
    return () => {
      alive = false;
    };
  }, [query, refresh, tick]);

  return (
    <Panel title="Research findings">
      <div className="space-y-3">
        <AreaPicker onChange={setAreaId} />
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Sector" htmlFor="f-sector">
            <select id="f-sector" value={sector} onChange={(e) => setSector(e.target.value)} className={inputClass}>
              <option value="">All sectors</option>
              {sectors.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}
            </select>
          </Field>
          <Field label="Status" htmlFor="f-status">
            <select id="f-status" value={status} onChange={(e) => setStatus(e.target.value)} className={inputClass}>
              <option value="">Current (not retired)</option>
              <option value="unverified">Unverified</option>
              <option value="source_verified">Source verified</option>
              <option value="disputed">Disputed</option>
              <option value="retired">Retired</option>
            </select>
          </Field>
        </div>
      </div>
      {error && <div className="mt-3"><FormMessage tone="error">{error}</FormMessage></div>}
      {items && items.length === 0 && (
        <p className="mt-4 text-sm text-muted">No findings match. Findings appear here after a source is analysed.</p>
      )}
      {items && items.length > 0 && (
        <ul className="mt-4 space-y-3">
          {items.map((f) => (
            <FindingCard key={f.id} f={f}>
              {canReview && <Review f={f} onDone={() => setTick((n) => n + 1)} />}
            </FindingCard>
          ))}
        </ul>
      )}
    </Panel>
  );
}

function Review({ f, onDone }: { f: ResearchFinding; onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<FindingStatus>(f.verification_status === "unverified" ? "source_verified" : f.verification_status);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)} className="mt-2 text-xs font-medium text-brand hover:underline">
        Review
      </button>
    );
  }
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await sendJson(`/api/v1/research/findings/${f.id}/review`, "POST", { status, note: note.trim() });
      setOpen(false);
      onDone();
    } catch (err) {
      setError(message(err, "The review could not be saved."));
    } finally {
      setBusy(false);
    }
  }
  const sid = `rv-s-${f.id}`;
  const nid = `rv-n-${f.id}`;
  return (
    <form onSubmit={save} className="mt-3 grid gap-2 border-t border-line pt-3 sm:grid-cols-[12rem_1fr_auto] sm:items-end">
      <Field label="Status" htmlFor={sid}>
        <select id={sid} value={status} onChange={(e) => setStatus(e.target.value as FindingStatus)} className={inputClass}>
          <option value="source_verified">Source verified</option>
          <option value="disputed">Disputed</option>
          <option value="unverified">Unverified</option>
          <option value="retired">Retired</option>
        </select>
      </Field>
      <Field label="What you checked" htmlFor={nid}>
        <input id={nid} required minLength={5} maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} className={inputClass} placeholder="e.g. Matched table 4 of the report" />
      </Field>
      <Button type="submit" busy={busy}>Save</Button>
      {error && <div className="sm:col-span-3"><FormMessage tone="error">{error}</FormMessage></div>}
    </form>
  );
}
