"use client";

import { useEffect, useId, useState } from "react";

import { inputClass } from "@/components/forms";
import { type AreaDetail, type AreaSummary, clientApi } from "@/lib/api";

/** State → LGA → ward selector. Reports the most specific area chosen. */
export function AreaPicker({ initialId, onChange }: { initialId?: number | null; onChange: (id: number | null) => void }) {
  const [states, setStates] = useState<AreaSummary[]>([]);
  const [lgas, setLgas] = useState<AreaSummary[]>([]);
  const [wards, setWards] = useState<AreaSummary[]>([]);
  const [sel, setSel] = useState({ state: "", lga: "", ward: "" });
  // Unique ids: several pages use this picker and Next.js can keep visited pages mounted.
  const uid = useId();

  useEffect(() => {
    clientApi<AreaSummary[]>("/api/v1/areas?level=state").then(setStates);
  }, []);

  useEffect(() => {
    if (!initialId) return;
    (async () => {
      const a = await clientApi<AreaDetail>(`/api/v1/areas/${initialId}`);
      const crumb = (l: string) => String(a.breadcrumbs.find((b) => b.level === l)?.id ?? "");
      const next = { state: crumb("state"), lga: crumb("lga"), ward: crumb("ward") };
      if (next.state) setLgas(await clientApi<AreaSummary[]>(`/api/v1/areas/${next.state}/children`));
      if (next.lga) setWards(await clientApi<AreaSummary[]>(`/api/v1/areas/${next.lga}/children`));
      setSel(next);
    })();
  }, [initialId]);

  async function pick(level: "state" | "lga" | "ward", value: string) {
    const next = { ...sel, [level]: value };
    if (level === "state") {
      next.lga = "";
      next.ward = "";
      setWards([]);
      setLgas(value ? await clientApi<AreaSummary[]>(`/api/v1/areas/${value}/children`) : []);
    }
    if (level === "lga") {
      next.ward = "";
      setWards(value ? await clientApi<AreaSummary[]>(`/api/v1/areas/${value}/children`) : []);
    }
    setSel(next);
    onChange(Number(next.ward || next.lga || next.state) || null);
  }

  const select = (id: string, label: string, value: string, options: AreaSummary[], level: "state" | "lga" | "ward", empty: string) => (
    <div>
      <label htmlFor={id} className="mb-1 block text-xs text-muted">{label}</label>
      <select id={id} data-level={level} value={value} disabled={options.length === 0} onChange={(e) => pick(level, e.target.value)} className={inputClass}>
        <option value="">{empty}</option>
        {options.map((o) => (
          <option key={o.id} value={o.id}>{o.name}</option>
        ))}
      </select>
    </div>
  );

  return (
    <div className="grid gap-3 sm:grid-cols-3">
      {select(`${uid}-state`, "State", sel.state, states, "state", "Choose a state")}
      {select(`${uid}-lga`, "LGA (optional)", sel.lga, lgas, "lga", "Whole state")}
      {select(`${uid}-ward`, "Ward (optional)", sel.ward, wards, "ward", "Whole LGA")}
    </div>
  );
}
