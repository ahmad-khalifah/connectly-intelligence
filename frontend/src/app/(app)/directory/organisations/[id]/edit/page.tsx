import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { Suspense } from "react";

import { SectionLoader } from "@/components/brand";
import { OrganisationForm } from "@/components/directory/OrganisationForm";
import { PageHeader } from "@/components/ui";
import type { AreaSummary } from "@/lib/api";
import type { Organisation, Vocabularies } from "@/lib/directory";
import { requireRole, serverApi } from "@/lib/server";

export const metadata: Metadata = { title: "Edit organisation" };

export default function EditOrganisationPage({ params }: PageProps<"/directory/organisations/[id]/edit">) {
  return (
    <div className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
      <PageHeader title="Edit organisation" />
      <Suspense fallback={<SectionLoader label="Loading form" />}>
        <Body params={params} />
      </Suspense>
    </div>
  );
}

async function Body({ params }: { params: PageProps<"/directory/organisations/[id]/edit">["params"] }) {
  const { id } = await params;
  const user = await requireRole("admin", "company");
  const [org, vocab, states] = await Promise.all([
    serverApi<Organisation>(`/api/v1/organisations/${Number(id) || 0}`),
    serverApi<Vocabularies>("/api/v1/directory/vocabularies"),
    serverApi<AreaSummary[]>("/api/v1/areas?level=state"),
  ]);
  if (user.role === "company" && user.organisation_id !== org.id) redirect(`/directory/organisations/${org.id}`);
  return <OrganisationForm vocab={vocab} states={states} initial={org} />;
}
