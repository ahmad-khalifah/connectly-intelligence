// Typed access to the Connectly Intelligence API. Types mirror backend/connectly/api/schemas.py.

export type Level = "country" | "state" | "lga" | "ward";

export const LEVEL_LABEL: Record<Level, string> = {
  country: "Country",
  state: "State",
  lga: "LGA",
  ward: "Ward",
};

export const LEVEL_PLURAL: Record<Level, string> = {
  country: "Countries",
  state: "States",
  lga: "Local Government Areas",
  ward: "Wards",
};

export interface DatasetRef {
  key: string;
  title: string;
  version: string | null;
  source_name: string;
  distributor: string | null;
  licence: string | null;
  licence_verified: boolean;
  attribution: string | null;
}

export interface Dataset extends DatasetRef {
  id: number;
  status: string;
  publication_date: string | null;
  source_update_text: string | null;
  reference_period: string | null;
  geographic_coverage: string | null;
  method_summary: string | null;
  limitations: string | null;
  licence_url: string | null;
  licence_evidence: string | null;
  commercial_use_allowed: boolean | null;
  landing_url: string | null;
  download_url: string | null;
  file_name: string | null;
  file_sha256: string | null;
  retrieved_at: string | null;
  record_count: number | null;
  level: string | null;
}

export interface AreaSummary {
  id: number;
  level: Level;
  name: string;
  parent_id: number | null;
  area_km2: number | null;
  child_count: number;
}

export interface AreaRef {
  id: number;
  level: Level;
  name: string;
}

export interface Notice {
  code: string;
  title: string;
  description: string;
}

export interface AreaDetail {
  id: number;
  level: Level;
  name: string;
  source_name: string;
  source_code: string;
  area_km2: number | null;
  centroid: [number, number] | null;
  bbox: [number, number, number, number] | null;
  breadcrumbs: AreaRef[];
  child_level: Level | null;
  child_count: number;
  aliases: string[];
  parent_method: string | null;
  parent_overlap: number | null;
  dataset: DatasetRef;
  notices: Notice[];
}

export interface Sector {
  code: string;
  name: string;
  description: string | null;
  is_priority: boolean;
  needs: { code: string; name: string }[];
  indicator_count: number;
  observation_count: number;
}

export interface DataGap {
  code: string;
  sector: string | null;
  title: string;
  description: string;
  geographic_scope: string;
  status: string;
  candidate_sources: string | null;
  needs_field_verification: boolean;
  identified_on: string | null;
}

export type Role = "admin" | "researcher" | "company" | "viewer";

export const ROLE_LABEL: Record<Role, string> = {
  admin: "Administrator",
  researcher: "Researcher",
  company: "Company",
  viewer: "Viewer",
};

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  must_change_password: boolean;
  organisation_id: number | null;
  last_login_at: string | null;
  created_at: string;
}

export interface Stats {
  areas_by_level: Record<Level, number>;
  settlements: number | null;
  settlements_verified?: number;
  facilities_by_kind?: Record<string, number>;
  claims?: number;
  claims_verified?: number;
  organisations_active?: number;
  solutions_published?: number;
  solutions_awaiting_review?: number;
  reports?: number;
  observations_by_sector?: Record<string, number>;
  focus_state?: {
    id: number;
    name: string;
    lgas: number;
    wards: number;
    population: number | null;
    facilities: number;
    settlements: number;
    claims: number;
  } | null;
  datasets_loaded: number;
  datasets_registered: number;
  sectors: number;
  indicators_defined: number;
  observations: number;
  open_data_gaps: number;
  generated_at: string;
}

export interface FeatureCollection {
  type: "FeatureCollection";
  features: GeoJSON.Feature[];
  simplified_tolerance_deg: number;
  attribution: string[];
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function errorDetail(res: Response): Promise<string> {
  try {
    const body = await res.json();
    const d = body.detail ?? res.statusText;
    // FastAPI validation errors are a list of {loc, msg}.
    if (Array.isArray(d)) {
      return d
        .map((e: { loc?: string[]; msg?: string }) =>
          [e.loc?.filter((l) => l !== "body").join("."), e.msg].filter(Boolean).join(": "),
        )
        .join("; ");
    }
    return String(d);
  } catch {
    return res.statusText || `HTTP ${res.status}`;
  }
}

/**
 * Browser-side calls go through this app's own server (/api/backend/...), which adds the
 * session from an httpOnly cookie. The browser never sees the session token.
 */
export async function clientApi<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api/backend${path}`, {
      cache: "no-store",
      ...init,
      headers: {
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiError(0, "Cannot reach the server. Check your connection.");
  }
  if (res.status === 401 && typeof window !== "undefined") {
    hardNavigate(`/login?next=${encodeURIComponent(window.location.pathname + window.location.search)}`);
  }
  if (!res.ok) throw new ApiError(res.status, await errorDetail(res));
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const sendJson = <T>(
  path: string,
  method: "POST" | "PUT" | "PATCH" | "DELETE",
  body?: unknown,
) =>
  clientApi<T>(path, { method, body: body === undefined ? undefined : JSON.stringify(body) });

export const formatNumber = (n: number | null | undefined, digits = 0) =>
  n == null
    ? "—"
    : n.toLocaleString("en-GB", {
        maximumFractionDigits: digits,
        minimumFractionDigits: 0,
      });

/** Only same-site paths may be used as a post-sign-in destination. */
export function safeNext(next: string | null | undefined): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) return "/";
  return next;
}

/**
 * Full page load. Used after sign-in state changes so no page rendered for the previous
 * session stays in the client-side router cache.
 */
export function hardNavigate(path: string) {
   
  window.location.assign(path);
}

export interface IndicatorInfo {
  code: string;
  name: string;
  unit: string | null;
  higher_is_worse: boolean | null;
  description: string | null;
  method: string | null;
  sector: string | null;
  values_by_level: Partial<Record<Level, number>>;
}

export interface ChoroplethValue {
  id: number;
  name: string;
  value: number;
  lower_bound: number | null;
  upper_bound: number | null;
  period: string;
  value_type: string;
  verification_status: string;
  dataset: string;
}

export interface ChoroplethResponse {
  indicator: { code: string; name: string; unit: string | null; higher_is_worse: boolean | null };
  level: Level;
  values: ChoroplethValue[];
  missing: { id: number; name: string }[];
  quintile_breaks: number[];
}

export function formatValue(v: number | null | undefined, unit: string | null | undefined) {
  if (v == null) return "—";
  const digits = Math.abs(v) >= 100 ? 0 : Math.abs(v) >= 10 ? 1 : 2;
  const n = formatNumber(v, digits);
  if (!unit) return n;
  if (unit === "%" || unit === "percent") return `${n}%`;
  return `${n} ${unit}`;
}

export interface ProfileValue {
  indicator: string;
  name: string;
  unit: string | null;
  sector: string | null;
  value: number | null;
  value_text: string | null;
  lower_bound: number | null;
  upper_bound: number | null;
  interval_note: string | null;
  period: string;
  value_type: string;
  verification_status: string;
  measured_at_level: Level;
  measured_at_area: string | null;
  is_context: boolean;
  higher_is_worse: boolean | null;
  dataset: string;
  dataset_title: string;
  licence: string | null;
  attribution: string | null;
  source_reference: string | null;
  note: string | null;
  updated_at: string | null;
}

export interface Claim {
  id: number;
  subject_type: "admin_area" | "settlement";
  subject_id: number;
  attribute: string;
  attribute_label: string;
  value_text: string;
  value_codes: string[] | null;
  value_type: string;
  source_description: string;
  source_url: string | null;
  observed_on: string | null;
  verification_status: string;
  verification_note?: string | null;
  verified_at?: string | null;
  is_active?: boolean;
  created_by_id?: number | null;
  created_by?: string | null;
  verified_by?: string | null;
  created_at: string;
  updated_at: string;
}

export interface AreaProfile {
  id: number;
  level: Level;
  name: string;
  state: string | null;
  lga: string | null;
  coordinates: { lon: number; lat: number; kind: string };
  area_km2: number | null;
  population: ProfileValue | null;
  urban_classification: ProfileValue | null;
  indicators: ProfileValue[];
  context_indicators: ProfileValue[];
  missing_indicators: { code: string; name: string; sector: string | null }[];
  facilities: { kind: string; total: number; with_status: number; datasets: string[] }[];
  facility_coverage: Record<string, string[]>;
  settlement_count: number | null;
  claims: Claim[];
  data_gaps: { code: string; title: string; description: string; sector: string | null; needs_field_verification: boolean }[];
  sectors: { code: string; name: string; is_priority: boolean }[];
  last_updated: string | null;
}

export interface NeedComponent {
  indicator: string;
  name: string;
  unit: string | null;
  higher_is_worse: boolean;
  weight: number;
  value: number;
  percentile: number;
  scope_median: number;
  value_type: string;
  verification_status: string;
  period: string;
  dataset: string;
  statement: string;
}

export interface NeedResult {
  id: number;
  name: string;
  parent_name: string | null;
  population: number | null;
  score: number | null;
  coverage: number;
  confidence: number | null;
  confidence_label: "high" | "medium" | "low" | "insufficient";
  components: NeedComponent[];
  missing: { indicator: string; name: string; weight: number; reason: string }[];
  rank: number | null;
}

export interface NeedAssessment {
  sector: string;
  sector_name: string;
  level: Level;
  scope: { id: number; name: string; level: Level };
  model: { code: string; weight: number; name: string; unit: string | null }[];
  status: "ok" | "insufficient" | "no_model";
  message: string | null;
  indicators: { code: string; name: string; weight: number; areas_with_value: number; used: boolean; reason: string | null }[];
  areas_in_scope?: number;
  areas_scored?: number;
  areas: NeedResult[];
}

export const CONFIDENCE_TONE = { high: "good", medium: "gold", low: "warn", insufficient: "neutral" } as const;

export interface MatchCriterion {
  key: string;
  label: string;
  weight: number;
  score: number | null;
  reason: string;
  evidence: string[];
}

export interface MatchResult {
  rank: number;
  solution: {
    id: number;
    name: string;
    summary: string;
    organisation_id: number;
    organisation_name: string;
    sector_name: string;
    verification_status: string;
    website: string | null;
  };
  availability: string | null;
  score: number;
  confidence: number;
  confidence_label: "high" | "medium" | "low";
  criteria_known: number;
  criteria: MatchCriterion[];
  strengths: string[];
  cautions: string[];
}

export interface MatchResponse {
  area: { id: number; name: string; level: Level };
  breadcrumbs: { id: number; name: string; level: Level }[];
  sector: string;
  sector_name: string;
  need: string | null;
  target_needs: { code: string; name: string }[];
  needs_basis: "selected" | "gap_evidence" | "none";
  gap_evidence: string[];
  area_languages: string[];
  status: "ok" | "no_matches" | "needs_unclear";
  message: string | null;
  results: MatchResult[];
  excluded: { id: number; name: string; organisation_name: string; reason: string }[];
}

export interface MarketItem {
  kind: "fact" | "derived" | "recommendation" | "gap";
  text: string;
  evidence: string[];
}

export interface MarketCandidate {
  id: number;
  name: string;
  state: string | null;
  level: Level;
  population: number | null;
  score: number | null;
  confidence: number;
  rank: number;
  components: Record<"gap" | "fit" | "reach" | "competition", number | null>;
  gap: { score: number | null; confidence_label: string; rank: number | null; evidence: string[] };
  fit: MatchCriterion[];
  need_evidenced: boolean;
  competitors: { id: number; name: string; organisation: string; availability: string }[];
}

export interface MarketEntryResult {
  sector: string;
  sector_name: string;
  objective: string;
  product: { id: number | null; name: string; source: string };
  needs: { code: string; name: string }[];
  level: Level;
  weights: Record<string, number>;
  candidates: MarketCandidate[];
  sections: { key: string; title: string; items: MarketItem[] }[];
}

export const ITEM_KIND: Record<MarketItem["kind"], { label: string; tone: "good" | "gold" | "brand" | "neutral" }> = {
  fact: { label: "Fact", tone: "good" },
  derived: { label: "Derived", tone: "gold" },
  recommendation: { label: "Recommendation", tone: "brand" },
  gap: { label: "Data gap", tone: "neutral" },
};

export interface BriefStatement {
  kind: MarketItem["kind"];
  text: string;
  cites: string[];
}

export interface BriefEvidence {
  id: string;
  kind: string;
  text: string;
  source: string;
  value_type: string | null;
  verification: string | null;
}

export interface IntelligenceBrief {
  area: { id: number; name: string; level: Level; place: string };
  sector: string;
  sector_name: string;
  question: string | null;
  sufficient_evidence: boolean;
  sections: { key: string; statements: BriefStatement[] }[];
  evidence: BriefEvidence[];
  narrative: {
    status: "accepted" | "rejected" | "disabled" | "insufficient" | "error" | "skipped";
    text: string | null;
    problems: string[];
    message: string | null;
    model?: string;
  };
}

export const BRIEF_SECTION: Record<string, string> = {
  profile: "Community profile",
  infrastructure: "Available infrastructure",
  gaps: "Identified service gaps",
  beneficiaries: "Potential beneficiary groups",
  barriers: "Technology adoption barriers",
  solutions: "Relevant available solutions",
  opportunities: "Implementation opportunities",
  limitations: "Data limitations",
  confidence: "Confidence",
  sources: "Supporting sources",
  related: "Related to your question",
};
