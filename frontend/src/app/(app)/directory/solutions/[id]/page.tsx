import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { SectionLoader } from "@/components/brand";
import { type Action, RecordActions } from "@/components/directory/RecordActions";
import { Badge, Panel } from "@/components/ui";
import type { User } from "@/lib/api";
import {
  formatPrice,
  label,
  type Solution,
  STATUS_LABEL,
  type Vocabularies,
  VERIFICATION_LABEL,
  verificationTone,
} from "@/lib/directory";
import { currentUser, serverApi } from "@/lib/server";

export const metadata: Metadata = { title: "Solution" };

export default function SolutionPage({ params }: PageProps<"/directory/solutions/[id]">) {
  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <Suspense fallback={<SectionLoader label="Loading solution" />}>
        <Body params={params} />
      </Suspense>
    </div>
  );
}

function actionsFor(s: Solution, user: User): Action[] {
  const path = `/api/v1/solutions/${s.id}`;
  const st = (key: string, labelText: string, status: string, extra: Partial<Action> = {}): Action => ({
    key,
    label: labelText,
    path: `${path}/status`,
    body: { status },
    ...extra,
  });
  if (user.role === "admin") {
    const a: Action[] = [];
    if (s.status !== "published") a.push(st("publish", "Publish", "published", { variant: "primary" }));
    if (s.status === "submitted") a.push(st("reject", "Reject", "rejected", { needsNote: "required", noteLabel: "Reason", variant: "danger" }));
    if (s.status !== "retired") a.push(st("retire", "Retire", "retired", { needsNote: "optional", variant: "danger" }));
    for (const v of ["source_verified", "field_verified", "disputed"] as const) {
      if (s.verification_status !== v)
        a.push({
          key: v,
          label: `Mark: ${VERIFICATION_LABEL[v].toLowerCase()}`,
          path: `${path}/verify`,
          body: { verification_status: v },
          needsNote: "required",
          noteLabel: "What was checked, and how",
        });
    }
    return a;
  }
  if (user.role === "company" && user.organisation_id === s.organisation_id) {
    if (s.status === "draft" || s.status === "rejected") return [st("submit", "Submit for review", "submitted", { variant: "primary" })];
    if (s.status === "submitted") return [st("withdraw", "Withdraw submission", "draft")];
    if (s.status === "published") return [st("retire", "Retire", "retired", { needsNote: "optional", variant: "danger" })];
  }
  return [];
}

function Row({ k, children }: { k: string; children: React.ReactNode }) {
  return (
    <>
      <dt className="text-muted">{k}</dt>
      <dd className="whitespace-pre-line">{children ?? <span className="text-muted">Not known</span>}</dd>
    </>
  );
}

const list = (codes: string[], vocab: Record<string, string>) =>
  codes.length ? codes.map((c) => vocab[c] ?? c).join(", ") : null;

async function Body({ params }: { params: PageProps<"/directory/solutions/[id]">["params"] }) {
  const { id } = await params;
  const [user, s, vocab] = await Promise.all([
    currentUser(),
    serverApi<Solution>(`/api/v1/solutions/${Number(id) || 0}`),
    serverApi<Vocabularies>("/api/v1/directory/vocabularies"),
  ]);
  const needNames = Object.fromEntries(vocab.sectors.flatMap((x) => x.needs.map((n) => [n.code, n.name])));
  const canEdit = user.role === "admin" || (user.role === "company" && user.organisation_id === s.organisation_id);
  const operating = s.coverage.filter((c) => c.kind === "operating");
  const expansion = s.coverage.filter((c) => c.kind === "expansion_interest");
  const actions = actionsFor(s, user);

  return (
    <div className="space-y-6">
      <nav className="text-sm text-muted">
        <Link href="/directory" className="hover:text-brand">
          Directory
        </Link>{" "}
        /{" "}
        <Link href={`/directory/organisations/${s.organisation_id}`} className="hover:text-brand">
          {s.organisation_name}
        </Link>
      </nav>
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap gap-1.5 text-xs">
            <Badge tone="brand">{s.sector_name}</Badge>
            <Badge tone={s.status === "published" ? "good" : "warn"}>{STATUS_LABEL[s.status]}</Badge>
            <Badge tone={verificationTone(s.verification_status)}>{VERIFICATION_LABEL[s.verification_status]}</Badge>
          </div>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight">{s.name}</h1>
          <p className="mt-1 max-w-3xl text-sm text-ink/85">{s.summary}</p>
        </div>
        {canEdit && s.status !== "retired" && (
          <Link href={`/directory/solutions/${s.id}/edit`} className="rounded-md border border-line px-4 py-2 text-sm font-medium hover:border-brand/40">
            Edit
          </Link>
        )}
      </header>

      {(actions.length > 0 || s.status_note || s.verification_note) && (
        <Panel title="Review">
          {s.status_note && <p className="mb-2 text-sm"><span className="text-muted">Status note: </span>{s.status_note}</p>}
          {s.verification_note && <p className="mb-3 text-sm"><span className="text-muted">Verification note: </span>{s.verification_note}</p>}
          <RecordActions actions={actions} />
        </Panel>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="What it does">
          <dl className="grid grid-cols-[9rem_1fr] gap-x-3 gap-y-2 text-sm">
            <Row k="Needs addressed">{s.need_codes.length ? s.need_codes.map((c) => needNames[c] ?? c).join(", ") : null}</Row>
            <Row k="Delivery">{label(vocab.delivery_models, s.delivery_model)}</Row>
            <Row k="Description">{s.description}</Row>
            <Row k="Beneficiaries">{list(s.beneficiary_groups, vocab.beneficiary_groups)}</Row>
            <Row k="In their words">{s.target_beneficiaries}</Row>
            <Row k="Evidence of impact">{s.evidence_of_impact}</Row>
            <Row k="Website">{s.website && <a href={s.website} className="text-brand hover:underline" rel="noopener noreferrer" target="_blank">{s.website}</a>}</Row>
          </dl>
        </Panel>
        <Panel title="Price and availability">
          <dl className="grid grid-cols-[9rem_1fr] gap-x-3 gap-y-2 text-sm">
            <Row k="Pricing model">{label(vocab.pricing_models, s.pricing_model)}</Row>
            <Row k="Price">{formatPrice(s)}</Row>
            <Row k="Pricing notes">{s.pricing_notes}</Row>
            <Row k="Operates in">{s.nationwide ? "Every state" : operating.length ? operating.map((c) => c.name).join(", ") : null}</Row>
            <Row k="Expansion interest">{expansion.length ? expansion.map((c) => c.name).join(", ") : "None stated"}</Row>
          </dl>
        </Panel>
        <Panel title="What users need">
          <dl className="grid grid-cols-[9rem_1fr] gap-x-3 gap-y-2 text-sm">
            <Row k="Internet">{label(vocab.internet_requirements, s.internet_requirement)}</Row>
            <Row k="Device">{label(vocab.device_requirements, s.device_requirement)}</Row>
            <Row k="Electricity">{label(vocab.power_requirements, s.power_requirement)}</Row>
            <Row k="Literacy">{label(vocab.literacy_requirements, s.literacy_requirement)}</Row>
            <Row k="Notes">{s.requirements_notes}</Row>
            <Row k="Languages">{list(s.languages, vocab.languages)}</Row>
            <Row k="Accessibility">{list(s.accessibility_features, vocab.accessibility_features)}</Row>
            <Row k="Accessibility notes">{s.accessibility_notes}</Row>
          </dl>
        </Panel>
        <Panel title="Distribution and partnerships">
          <dl className="grid grid-cols-[9rem_1fr] gap-x-3 gap-y-2 text-sm">
            <Row k="Channels">{list(s.distribution_channels, vocab.distribution_channels)}</Row>
            <Row k="Requirements">{s.distribution_notes}</Row>
            <Row k="Partnerships sought">{list(s.partnership_types, vocab.partnership_types)}</Row>
            <Row k="Partnership notes">{s.partnership_notes}</Row>
            <Row k="Implementation">{s.implementation_notes}</Row>
          </dl>
        </Panel>
      </div>

      <Panel title="Source">
        <dl className="grid grid-cols-[9rem_1fr] gap-x-3 gap-y-2 text-sm">
          <Row k="Source">{s.source_description}</Row>
          <Row k="Link">{s.source_url && <a href={s.source_url} className="break-all text-brand hover:underline" rel="noopener noreferrer" target="_blank">{s.source_url}</a>}</Row>
          <Row k="Last updated">{new Date(s.updated_at).toLocaleString("en-GB")}</Row>
          {s.created_by && <Row k="Entered by">{s.created_by}</Row>}
        </dl>
      </Panel>
    </div>
  );
}
