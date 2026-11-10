import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { SectionLoader } from "@/components/brand";
import { SolutionCard } from "@/components/directory/SolutionCard";
import { inputClass } from "@/components/forms";
import { Badge, PageHeader, Panel } from "@/components/ui";
import type { AreaSummary } from "@/lib/api";
import type { Organisation, Solution, Vocabularies } from "@/lib/directory";
import { currentUser, serverApi } from "@/lib/server";

export const metadata: Metadata = { title: "Technology directory" };

export default function DirectoryPage({ searchParams }: PageProps<"/directory">) {
  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <PageHeader
        title="Technology directory"
        lead="Organisations and the solutions they offer, with what each needs to work: internet, devices, power, languages and distribution. Every record shows its source and whether it has been checked."
      />
      <Suspense fallback={<SectionLoader label="Loading directory" />}>
        <Directory searchParams={searchParams} />
      </Suspense>
    </div>
  );
}

const one = (v: string | string[] | undefined) => (typeof v === "string" ? v : "");

async function Directory({ searchParams }: { searchParams: PageProps<"/directory">["searchParams"] }) {
  const sp = await searchParams;
  const sector = one(sp.sector);
  const q = one(sp.q);
  const state = one(sp.state);
  const status = one(sp.status);
  const tab = one(sp.tab) === "organisations" ? "organisations" : "solutions";
  const params = new URLSearchParams();
  if (sector) params.set("sector", sector);
  if (q.length >= 2) params.set("q", q);
  if (state) params.set("area_id", state);
  if (status) params.set("status", status);

  const [user, vocab, states, solutions, orgs] = await Promise.all([
    currentUser(),
    serverApi<Vocabularies>("/api/v1/directory/vocabularies"),
    serverApi<AreaSummary[]>("/api/v1/areas?level=state"),
    serverApi<Solution[]>(`/api/v1/solutions?${params}`),
    serverApi<Organisation[]>(`/api/v1/organisations${q.length >= 2 ? `?q=${encodeURIComponent(q)}` : ""}`),
  ]);
  const isAdmin = user.role === "admin";
  const pending = isAdmin ? solutions.filter((s) => s.status === "submitted").length : 0;
  const tabLink = (t: string) => {
    const p = new URLSearchParams(params);
    p.delete("area_id");
    if (state) p.set("state", state);
    p.set("tab", t);
    return `/directory?${p}`;
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        {isAdmin && (
          <Link href="/directory/organisations/new" className="rounded-md bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-strong">
            Add organisation
          </Link>
        )}
        {user.role === "company" &&
          (user.organisation_id ? (
            <Link href={`/directory/organisations/${user.organisation_id}`} className="rounded-md bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-strong">
              Your organisation
            </Link>
          ) : (
            <Link href="/directory/organisations/new" className="rounded-md bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-strong">
              Register your organisation
            </Link>
          ))}
        {isAdmin && pending > 0 && (
          <Link href="/directory?status=submitted" className="text-sm text-gold-ink underline-offset-2 hover:underline">
            {pending} awaiting review
          </Link>
        )}
      </div>

      <form method="get" className="grid gap-3 rounded-lg border border-line bg-panel p-4 md:grid-cols-[1.4fr_1fr_1fr_auto] md:items-end">
        <input type="hidden" name="tab" value={tab} />
        <div>
          <label htmlFor="q" className="mb-1 block text-xs text-muted">
            Search
          </label>
          <input id="q" name="q" defaultValue={q} placeholder="Name, organisation or description" className={inputClass} />
        </div>
        <div>
          <label htmlFor="sector" className="mb-1 block text-xs text-muted">
            Sector
          </label>
          <select id="sector" name="sector" defaultValue={sector} className={inputClass}>
            <option value="">All sectors</option>
            {vocab.sectors.map((s) => (
              <option key={s.code} value={s.code}>
                {s.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="state" className="mb-1 block text-xs text-muted">
            Show availability in
          </label>
          <select id="state" name="state" defaultValue={state} className={inputClass}>
            <option value="">Any state</option>
            {states.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </div>
        <button type="submit" className="rounded-md border border-line px-4 py-2 text-sm font-medium hover:border-brand/40">
          Apply
        </button>
      </form>

      <div role="tablist" className="flex gap-1 border-b border-line text-sm">
        {(["solutions", "organisations"] as const).map((t) => (
          <Link
            key={t}
            role="tab"
            aria-selected={tab === t}
            href={tabLink(t)}
            className={`-mb-px border-b-2 px-3 py-2 capitalize ${tab === t ? "border-gold font-medium text-brand" : "border-transparent text-muted hover:text-ink"}`}
          >
            {t} ({t === "solutions" ? solutions.length : orgs.length})
          </Link>
        ))}
      </div>

      {tab === "solutions" ? (
        solutions.length === 0 ? (
          <EmptyDirectory filtered={Boolean(sector || q || status)} />
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {solutions.map((s) => (
              <SolutionCard key={s.id} s={s} vocab={vocab} showStatus={user.role !== "viewer" && user.role !== "researcher"} />
            ))}
          </div>
        )
      ) : orgs.length === 0 ? (
        <EmptyDirectory filtered={Boolean(q)} />
      ) : (
        <Panel>
          <ul className="divide-y divide-line">
            {orgs.map((o) => (
              <li key={o.id} className="flex flex-wrap items-center justify-between gap-2 py-3 first:pt-0 last:pb-0">
                <div>
                  <Link href={`/directory/organisations/${o.id}`} className="font-medium hover:text-brand">
                    {o.name}
                  </Link>
                  <div className="text-xs text-muted">
                    {vocab.org_types[o.org_type]} · {[o.headquarters, o.headquarters_state, o.headquarters_country].filter(Boolean).join(", ")}
                  </div>
                </div>
                <div className="flex flex-wrap gap-1.5 text-xs">
                  {o.status !== "active" && <Badge tone="warn">{o.status}</Badge>}
                  <Badge>{o.published_solutions} published</Badge>
                </div>
              </li>
            ))}
          </ul>
        </Panel>
      )}
    </div>
  );
}

function EmptyDirectory({ filtered }: { filtered: boolean }) {
  return (
    <div className="rounded-lg border border-dashed border-line bg-panel px-6 py-10 text-center">
      <p className="font-medium">{filtered ? "Nothing matches these filters." : "The directory is empty."}</p>
      {!filtered && (
        <p className="mx-auto mt-2 max-w-xl text-sm text-muted">
          There is no open register of technology solutions for Nigeria, so records are added by
          administrators from company sources, or submitted by companies for review. Nothing is
          added automatically.
        </p>
      )}
    </div>
  );
}
