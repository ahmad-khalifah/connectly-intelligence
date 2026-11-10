import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { Suspense } from "react";

import { SectionLoader } from "@/components/brand";
import { SolutionForm } from "@/components/directory/SolutionForm";
import { PageHeader } from "@/components/ui";
import type { AreaSummary } from "@/lib/api";
import type { Organisation, Vocabularies } from "@/lib/directory";
import { requireRole, serverApi } from "@/lib/server";

export const metadata: Metadata = { title: "New solution" };

export default function NewSolutionPage({ params }: PageProps<"/directory/organisations/[id]/solutions/new">) {
  return (
    <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
      <PageHeader title="New solution" />
      <Suspense fallback={<SectionLoader label="Loading form" />}>
        <Body params={params} />
      </Suspense>
    </div>
  );
}

async function Body({ params }: { params: PageProps<"/directory/organisations/[id]/solutions/new">["params"] }) {
  const { id } = await params;
  const user = await requireRole("admin", "company");
  const [org, vocab, states] = await Promise.all([
    serverApi<Organisation>(`/api/v1/organisations/${Number(id) || 0}`),
    serverApi<Vocabularies>("/api/v1/directory/vocabularies"),
    serverApi<AreaSummary[]>("/api/v1/areas?level=state"),
  ]);
  if (user.role === "company" && user.organisation_id !== org.id) redirect(`/directory/organisations/${org.id}`);
  return (
    <>
      <p className="mb-6 text-sm text-muted">For {org.name}. New solutions start as drafts.</p>
      <SolutionForm vocab={vocab} states={states} organisationId={org.id} />
    </>
  );
}
