import type { Metadata } from "next";
import { Suspense } from "react";

import { SectionLoader } from "@/components/brand";
import { OrganisationForm } from "@/components/directory/OrganisationForm";
import { PageHeader } from "@/components/ui";
import type { AreaSummary } from "@/lib/api";
import type { Vocabularies } from "@/lib/directory";
import { requireRole, serverApi } from "@/lib/server";

export const metadata: Metadata = { title: "New organisation" };

export default function NewOrganisationPage() {
  return (
    <div className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
      <PageHeader title="New organisation" />
      <Suspense fallback={<SectionLoader label="Loading form" />}>
        <Body />
      </Suspense>
    </div>
  );
}

async function Body() {
  const user = await requireRole("admin", "company");
  const [vocab, states] = await Promise.all([
    serverApi<Vocabularies>("/api/v1/directory/vocabularies"),
    serverApi<AreaSummary[]>("/api/v1/areas?level=state"),
  ]);
  return (
    <>
      {user.role === "company" && (
        <p className="mb-6 text-sm text-muted">
          Your organisation will be reviewed by a Connectly administrator before it appears to other users.
        </p>
      )}
      <OrganisationForm vocab={vocab} states={states} />
    </>
  );
}
