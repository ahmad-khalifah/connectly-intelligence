import type { Metadata } from "next";
import { Suspense } from "react";

import { SectionLoader } from "@/components/brand";
import { Research } from "@/components/research/Research";
import { PageHeader } from "@/components/ui";
import type { ResearchStatus, ResearchZone, Sector } from "@/lib/api";
import { currentUser, serverApi } from "@/lib/server";

export const metadata: Metadata = { title: "Research" };

export default function ResearchPage() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <PageHeader
        title="Research"
        lead="Search the web with Gemini and Google Search, then turn the sources you trust into findings. Live answers are AI-generated, shown only to you and not stored. Findings are kept only from sources you submit, with a quote checked word for word against the source, and stay unverified until a researcher reviews them."
      />
      <Suspense fallback={<SectionLoader label="Loading" />}>
        <Body />
      </Suspense>
    </div>
  );
}

async function Body() {
  const [status, zones, sectors, user] = await Promise.all([
    serverApi<ResearchStatus>("/api/v1/research/status"),
    serverApi<ResearchZone[]>("/api/v1/research/zones"),
    serverApi<Sector[]>("/api/v1/sectors"),
    currentUser(),
  ]);
  return (
    <Research
      status={status}
      zones={zones}
      sectors={sectors.map((s) => ({ code: s.code, name: s.name }))}
      canResearch={user.role === "admin" || user.role === "researcher"}
    />
  );
}
