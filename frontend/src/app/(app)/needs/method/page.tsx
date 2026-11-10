import type { Metadata } from "next";
import { Suspense } from "react";

import { SectionLoader } from "@/components/brand";
import { PageHeader, Panel } from "@/components/ui";
import { serverApi } from "@/lib/server";

export const metadata: Metadata = { title: "Needs assessment method" };

interface Model {
  sector: string;
  sector_name: string;
  has_model: boolean;
  indicators: { code: string; name: string; weight: number; unit: string | null; higher_is_worse: boolean | null }[];
}

export default function MethodPage() {
  return (
    <div className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
      <PageHeader title="How gap scores are worked out" />
      <div className="space-y-6 text-sm leading-relaxed">
        <Panel title="Method">
          <ol className="list-decimal space-y-2 pl-5">
            <li>Choose a sector and a group of comparable areas: all states, or the LGAs or wards of one state.</li>
            <li>For each indicator in the sector, rank the areas that have a value measured at their own level. A state survey figure is the same for every ward in the state, so it is not used to rank wards; it appears on profiles as context.</li>
            <li>An indicator is used only if at least three areas in the group have a value.</li>
            <li>Each area gets a percentile per indicator: 100 means it is the least served in the group, 0 the best served. Ties share the average.</li>
            <li>The gap score is the weighted average of the percentiles the area has.</li>
            <li>Coverage is the share of the sector&apos;s indicator weight that is available for the area. With less than 34%, no score is given.</li>
            <li>Confidence = coverage × quality of the values used. Quality: measured 1.0, derived 0.85, modelled 0.7, estimate 0.6, assumption 0.3, AI-generated 0; ×0.9 if not verified, ×0.5 if disputed. High ≥ 0.6, medium ≥ 0.35, otherwise low.</li>
          </ol>
          <p className="mt-3 text-muted">Scores are relative. A high score means an area is worse served than most comparable areas on the evidence loaded. It does not measure absolute need, and it changes when data is added.</p>
        </Panel>
        <Suspense fallback={<SectionLoader label="Loading indicators" />}>
          <Models />
        </Suspense>
      </div>
    </div>
  );
}

async function Models() {
  const models = await serverApi<Model[]>("/api/v1/needs/models");
  return (
    <Panel title="Indicators and weights">
      <div className="space-y-4">
        {models.map((m) => (
          <div key={m.sector}>
            <h3 className="font-semibold">{m.sector_name}</h3>
            {m.has_model ? (
              <ul className="mt-1 space-y-0.5">
                {m.indicators.map((i) => (
                  <li key={i.code} className="flex justify-between gap-4">
                    <span>
                      {i.name} <span className="text-xs text-muted">({i.higher_is_worse ? "higher is worse" : "lower is worse"})</span>
                    </span>
                    <span className="tabular-nums text-muted">{Math.round(i.weight * 100)}%</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-muted">No open indicator is available for this sector yet, so it is not scored.</p>
            )}
          </div>
        ))}
      </div>
    </Panel>
  );
}
