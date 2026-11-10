import { Suspense } from "react";

import Explorer from "@/components/explorer/Explorer";
import { PageHeader } from "@/components/ui";

export default function ExplorerPage() {
  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <PageHeader
        title="Explorer"
        lead="Browse Nigeria from country to state to LGA. Click an area on the map or in the list. Wards and communities appear here as their datasets are loaded; until then the gap is shown."
      />
      <Suspense fallback={<p className="text-sm text-muted">Loading explorer…</p>}>
        <Explorer />
      </Suspense>
    </div>
  );
}
