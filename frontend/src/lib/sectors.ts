// Links between sectors, facility kinds and claim attributes, used to group evidence.

export const SECTOR_FACILITY_KIND: Record<string, string> = {
  health: "health",
  education: "education",
  finance: "financial",
  connectivity: "telecom",
  energy: "energy",
  commerce: "market",
  transport: "transport",
  agriculture: "agriculture",
};

export const FACILITY_KIND_LABEL: Record<string, string> = {
  health: "Health facilities",
  education: "Schools",
  financial: "Financial access points",
  telecom: "Mobile network sites",
  energy: "Energy infrastructure",
  market: "Markets",
  transport: "Transport facilities",
  agriculture: "Agricultural facilities",
  community: "Community facilities",
  other: "Other facilities",
};

export const CLAIM_SECTOR: Record<string, string | null> = {
  economic_activities: "commerce",
  languages: null,
  market_days: "commerce",
  community_organisations: null,
  infrastructure_notes: null,
  connectivity_notes: "connectivity",
  energy_notes: "energy",
  agriculture_notes: "agriculture",
  access_notes: "transport",
  other: null,
};

export const VALUE_TYPE_LABEL: Record<string, string> = {
  measured: "Measured",
  estimated: "Estimate",
  modelled: "Modelled",
  derived: "Derived",
  assumed: "Assumption",
  ai_generated: "AI-generated",
};

export const valueTypeTone = (t: string) =>
  t === "measured" ? "good" : t === "assumed" || t === "ai_generated" ? "bad" : "gold";

// Sequential classes from the brand palette: cream → gold → maroon (monotonic lightness).
export const CHOROPLETH = ["#f7ede4", "#ebcfa6", "#d9a441", "#a4513a", "#6b1420"];
export const NO_DATA = "#e4e0dc";

/** Strictly increasing thresholds and one colour per class (MapLibre needs ascending stops). */
export function classes(breaks: number[]): { stops: number[]; colors: string[] } {
  const stops = breaks.filter((b, i) => i === 0 || b > breaks[i - 1]);
  const k = stops.length + 1;
  const colors =
    k === 1 ? [CHOROPLETH[4]] : Array.from({ length: k }, (_, i) => CHOROPLETH[Math.round((i * 4) / (k - 1))]);
  return { stops, colors };
}
