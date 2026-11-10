import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { Suspense } from "react";

import { SectionLoader } from "@/components/brand";
import { SolutionForm } from "@/components/directory/SolutionForm";
import { PageHeader } from "@/components/ui";
import type { AreaSummary } from "@/lib/api";
import type { Solution, Vocabularies } from "@/lib/directory";
import { requireRole, serverApi } from "@/lib/server";

export const metadata: Metadata = { title: "Edit solution" };

export default function EditSolutionPage({ params }: PageProps<"/directory/solutions/[id]/edit">) {
  return (
    <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
      <PageHeader title="Edit solution" />
      <Suspense fallback={<SectionLoader label="Loading form" />}>
        <Body params={params} />
      </Suspense>
    </div>
  );
}

async function Body({ params }: { params: PageProps<"/directory/solutions/[id]/edit">["params"] }) {
  const { id } = await params;
  const user = await requireRole("admin", "company");
  const [s, vocab, states] = await Promise.all([
    serverApi<Solution>(`/api/v1/solutions/${Number(id) || 0}`),
    serverApi<Vocabularies>("/api/v1/directory/vocabularies"),
    serverApi<AreaSummary[]>("/api/v1/areas?level=state"),
  ]);
  if (user.role === "company" && user.organisation_id !== s.organisation_id) redirect(`/directory/solutions/${s.id}`);
  return (
    <>
      {user.role === "company" && s.status === "published" && (
        <p className="mb-6 rounded-md border border-gold/40 bg-gold-soft px-3 py-2 text-sm text-gold-ink">
          Saving changes sends this solution back for review. It is hidden from other users until an administrator publishes it again.
        </p>
      )}
      <SolutionForm vocab={vocab} states={states} organisationId={s.organisation_id} initial={s} />
    </>
  );
}
