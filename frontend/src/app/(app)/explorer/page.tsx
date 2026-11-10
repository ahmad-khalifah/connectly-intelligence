import { Suspense } from "react";

import Explorer from "@/components/explorer/Explorer";
import { PageHeader } from "@/components/ui";

export default function ExplorerPage() {
  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <PageHeader
        title="Explorer"
        lead="Browse Nigeria from country to state, LGA and ward. Colour areas by any indicator that has values at that level, add facility and settlement points, and open any area's profile. Areas without a value are shown as such, never filled from a larger area."
      />
      <Suspense fallback={<p className="text-sm text-muted">Loading explorer…</p>}>
        <Explorer />
      </Suspense>
    </div>
  );
}
