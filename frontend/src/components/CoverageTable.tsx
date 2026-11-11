import Link from "next/link";

import { formatNumber, type NationalCoverage } from "@/lib/api";

// State-by-state data coverage across Nigeria. A blank cell means no loaded dataset covers
// that state for that layer: the data is missing there, not zero.
export default function CoverageTable({ coverage }: { coverage: NationalCoverage }) {
  const { layers, states, states_total: total } = coverage;
  return (
    <div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[760px] text-sm">
          <caption className="sr-only">Data coverage by state</caption>
          <thead>
            <tr className="text-left align-bottom text-xs text-muted">
              <th scope="col" className="sticky left-0 bg-panel pb-2 pr-3 font-normal">State</th>
              <th scope="col" className="pb-2 pr-3 text-right font-normal">LGAs</th>
              {layers.map((l) => (
                <th key={l.code} scope="col" className="pb-2 pr-3 text-right font-normal" title={l.count_meaning}>
                  <div>{l.label}</div>
                  <div className={l.states_covered === total ? "text-brand" : "text-gold-ink"}>
                    {l.states_covered}/{total} states
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {states.map((s) => (
              <tr key={s.id} className="border-t border-line">
                <th scope="row" className="sticky left-0 bg-panel py-1.5 pr-3 text-left font-normal">
                  <Link href={`/areas/${s.id}`} className="text-brand hover:underline">{s.name}</Link>
                </th>
                <td className="py-1.5 pr-3 text-right tabular-nums">{s.lgas}</td>
                {layers.map((l) => {
                  const c = s.layers[l.code];
                  const label = c?.covered
                    ? `${l.label} in ${s.name}: ${formatNumber(c.records)} (${l.count_meaning}), source ${c.source}`
                    : c?.partial
                      ? `${l.label} in ${s.name}: partial, ${formatNumber(c.records)} of ${formatNumber(s.wards)} wards`
                      : `${l.label}: no dataset covers ${s.name}`;
                  return (
                    <td key={l.code} className="py-1.5 pr-3 text-right tabular-nums" title={label}>
                      {c?.covered ? (
                        formatNumber(c.records)
                      ) : c?.partial ? (
                        <span className="text-gold-ink">partial</span>
                      ) : (
                        <span className="text-muted/60" aria-label="not covered">—</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-xs text-muted">
        A number means a loaded dataset covers that state; it counts records from the one source
        used there. A dash means no dataset covers the state yet: the data is missing, not zero,
        and that state gets no value for indicators built from it. Point at a cell for its source.
      </p>
    </div>
  );
}
