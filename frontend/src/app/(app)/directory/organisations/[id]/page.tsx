import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { SectionLoader } from "@/components/brand";
import { type Action, RecordActions } from "@/components/directory/RecordActions";
import { SolutionCard } from "@/components/directory/SolutionCard";
import { Badge, Panel } from "@/components/ui";
import { type Organisation, type Vocabularies, VERIFICATION_LABEL, verificationTone } from "@/lib/directory";
import { currentUser, serverApi } from "@/lib/server";

export const metadata: Metadata = { title: "Organisation" };

export default function OrganisationPage({ params }: PageProps<"/directory/organisations/[id]">) {
  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <Suspense fallback={<SectionLoader label="Loading organisation" />}>
        <Body params={params} />
      </Suspense>
    </div>
  );
}

async function Body({ params }: { params: PageProps<"/directory/organisations/[id]">["params"] }) {
  const { id } = await params;
  const [user, org, vocab] = await Promise.all([
    currentUser(),
    serverApi<Organisation>(`/api/v1/organisations/${Number(id) || 0}`),
    serverApi<Vocabularies>("/api/v1/directory/vocabularies"),
  ]);
  const isAdmin = user.role === "admin";
  const owns = user.role === "company" && user.organisation_id === org.id;
  const path = `/api/v1/organisations/${org.id}/review`;
  const actions: Action[] = isAdmin
    ? [
        ...(org.status !== "active" ? [{ key: "approve", label: "Approve", path, body: { status: "active" }, needsNote: "required" as const, noteLabel: "What was checked", variant: "primary" as const }] : []),
        ...(org.status === "submitted" ? [{ key: "reject", label: "Reject", path, body: { status: "rejected" }, needsNote: "required" as const, noteLabel: "Reason", variant: "danger" as const }] : []),
        ...(org.verification_status !== "source_verified" ? [{ key: "verify", label: "Mark: checked against source", path, body: { verification_status: "source_verified" }, needsNote: "required" as const, noteLabel: "What was checked, and how" }] : []),
        ...(org.status === "active" ? [{ key: "retire", label: "Retire", path, body: { status: "retired" }, needsNote: "required" as const, noteLabel: "Reason", variant: "danger" as const }] : []),
      ]
    : [];

  return (
    <div className="space-y-6">
      <nav className="text-sm text-muted">
        <Link href="/directory?tab=organisations" className="hover:text-brand">
          Directory
        </Link>
      </nav>
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap gap-1.5 text-xs">
            <Badge>{vocab.org_types[org.org_type]}</Badge>
            {org.status !== "active" && <Badge tone="warn">{org.status}</Badge>}
            <Badge tone={verificationTone(org.verification_status)}>{VERIFICATION_LABEL[org.verification_status]}</Badge>
          </div>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight">{org.name}</h1>
          {org.industry && <p className="text-sm text-muted">{org.industry}</p>}
        </div>
        <div className="flex gap-2">
          {(isAdmin || owns) && (
            <>
              <Link href={`/directory/organisations/${org.id}/edit`} className="rounded-md border border-line px-4 py-2 text-sm font-medium hover:border-brand/40">
                Edit
              </Link>
              {org.status !== "rejected" && org.status !== "retired" && (
                <Link href={`/directory/organisations/${org.id}/solutions/new`} className="rounded-md bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-strong">
                  Add solution
                </Link>
              )}
            </>
          )}
        </div>
      </header>
      {owns && org.status === "submitted" && (
        <p className="rounded-md border border-gold/40 bg-gold-soft px-3 py-2 text-sm text-gold-ink">
          Your organisation is awaiting review by a Connectly administrator. You can add solutions now; they are published after review.
        </p>
      )}
      {(actions.length > 0 || org.verification_note) && (
        <Panel title="Review">
          {org.verification_note && <p className="mb-3 text-sm"><span className="text-muted">Note: </span>{org.verification_note}</p>}
          <RecordActions actions={actions} />
        </Panel>
      )}
      <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
        <Panel title="About">
          {org.description ? <p className="whitespace-pre-line text-sm">{org.description}</p> : <p className="text-sm text-muted">No description given.</p>}
        </Panel>
        <Panel title="Details">
          <dl className="grid grid-cols-[6.5rem_1fr] gap-y-2 text-sm">
            <dt className="text-muted">Headquarters</dt>
            <dd>{[org.headquarters, org.headquarters_state, org.headquarters_country].filter(Boolean).join(", ")}</dd>
            <dt className="text-muted">Website</dt>
            <dd className="break-all">{org.website ? <a className="text-brand hover:underline" href={org.website} rel="noopener noreferrer" target="_blank">{org.website}</a> : "—"}</dd>
            <dt className="text-muted">Source</dt>
            <dd>{org.source_description}{org.source_url && <> · <a className="text-brand hover:underline" href={org.source_url} rel="noopener noreferrer" target="_blank">link</a></>}</dd>
            <dt className="text-muted">Updated</dt>
            <dd>{new Date(org.updated_at).toLocaleDateString("en-GB")}</dd>
          </dl>
        </Panel>
      </div>
      <section>
        <h2 className="mb-3 text-lg font-semibold">Solutions</h2>
        {org.solutions && org.solutions.length > 0 ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {org.solutions.map((s) => (
              <SolutionCard key={s.id} s={s} vocab={vocab} showStatus={isAdmin || owns} />
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted">No solutions listed.</p>
        )}
      </section>
    </div>
  );
}
