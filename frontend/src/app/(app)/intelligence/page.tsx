import type { Metadata } from "next";
import { Suspense } from "react";

import { SectionLoader } from "@/components/brand";
import { Intelligence } from "@/components/intelligence/Intelligence";
import { PageHeader } from "@/components/ui";
import type { Sector } from "@/lib/api";
import { serverApi } from "@/lib/server";

export const metadata: Metadata = { title: "Intelligence brief" };

export default function IntelligencePage() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <PageHeader
        title="Intelligence brief"
        lead="Everything the platform knows about a community and sector, in eleven sections: profile, infrastructure, gaps, beneficiaries, barriers, solutions, opportunities, research findings, limitations, confidence and sources. Every statement cites its evidence."
      />
      <Suspense fallback={<SectionLoader label="Loading" />}>
        <Body />
      </Suspense>
    </div>
  );
}

async function Body() {
  const [sectors, ai] = await Promise.all([
    serverApi<Sector[]>("/api/v1/sectors"),
    serverApi<{ enabled: boolean; model: string | null; provider: string }>("/api/v1/intelligence/status"),
  ]);
  return <Intelligence sectors={sectors} ai={ai} />;
}
