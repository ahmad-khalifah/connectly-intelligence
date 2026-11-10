import type { Metadata } from "next";
import { Suspense } from "react";

import { SectionLoader } from "@/components/brand";
import { Matching } from "@/components/matching/Matching";
import { PageHeader } from "@/components/ui";
import type { Vocabularies } from "@/lib/directory";
import { serverApi } from "@/lib/server";

export const metadata: Metadata = { title: "Technology matching" };

export default function MatchingPage() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <PageHeader
        title="Technology matching"
        lead="Choose a community and a sector. Published solutions that address the need are ranked on eight criteria: relevance, suitability, availability, affordability, internet and devices, language, distribution and feasibility. Each criterion shows its evidence, or says it is unknown."
      />
      <Suspense fallback={<SectionLoader label="Loading" />}>
        <Body />
      </Suspense>
    </div>
  );
}

async function Body() {
  const vocab = await serverApi<Vocabularies>("/api/v1/directory/vocabularies");
  return <Matching vocab={vocab} />;
}
