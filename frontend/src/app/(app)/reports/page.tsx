import type { Metadata } from "next";
import { Suspense } from "react";

import { SectionLoader } from "@/components/brand";
import { ReportList } from "@/components/reports/ReportList";
import { PageHeader } from "@/components/ui";
import { currentUser, serverApi } from "@/lib/server";

export const metadata: Metadata = { title: "Reports" };

export interface ReportRow {
  id: number;
  kind: "brief" | "needs" | "matching" | "market_entry";
  title: string;
  created_at: string;
  created_by: string | null;
}

export default function ReportsPage() {
  return (
    <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
      <PageHeader
        title="Reports"
        lead="Saved analyses. Each is a snapshot of the data at the time it was saved and can be downloaded as a branded PDF. Save a report from the Intelligence, Needs, Matching or Market entry pages."
      />
      <Suspense fallback={<SectionLoader label="Loading reports" />}>
        <Body />
      </Suspense>
    </div>
  );
}

async function Body() {
  const [user, reports] = await Promise.all([currentUser(), serverApi<ReportRow[]>("/api/v1/reports")]);
  return <ReportList initial={reports} showAuthor={user.role === "admin"} />;
}
