import type { Metadata } from "next";
import { Suspense } from "react";

import { SectionLoader } from "@/components/brand";
import { MarketEntry } from "@/components/market/MarketEntry";
import { PageHeader } from "@/components/ui";
import type { AreaSummary } from "@/lib/api";
import type { Solution, Vocabularies } from "@/lib/directory";
import { serverApi } from "@/lib/server";

export const metadata: Metadata = { title: "Market entry" };

export default function MarketEntryPage() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <PageHeader
        title="Market entry"
        lead="Where a product could start, which channels and languages the evidence supports, what competes with it, and what is not yet known. Each finding is labelled as fact, derived, recommendation or data gap."
      />
      <Suspense fallback={<SectionLoader label="Loading" />}>
        <Body />
      </Suspense>
    </div>
  );
}

async function Body() {
  const [vocab, states, objectives, solutions] = await Promise.all([
    serverApi<Vocabularies>("/api/v1/directory/vocabularies"),
    serverApi<AreaSummary[]>("/api/v1/areas?level=state"),
    serverApi<Record<string, string>>("/api/v1/market-entry/objectives"),
    serverApi<Solution[]>("/api/v1/solutions"),
  ]);
  return <MarketEntry vocab={vocab} states={states} objectives={objectives} solutions={solutions} />;
}
