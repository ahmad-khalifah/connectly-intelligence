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

export interface Stats {
  areas_by_level: Record<Level, number>;
  settlements: number | null;
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

// Server components use API_URL (container-to-container in production);
// the browser uses NEXT_PUBLIC_API_URL.
export const PUBLIC_API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const SERVER_API_URL = process.env.API_URL ?? PUBLIC_API_URL;

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function get<T>(base: string, path: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${base}${path}`, { cache: "no-store" });
  } catch {
    throw new ApiError(0, `Cannot reach the API at ${base}. Is the backend running?`);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* body was not JSON */
    }
    throw new ApiError(res.status, String(detail));
  }
  return res.json() as Promise<T>;
}

export const serverApi = <T>(path: string) => get<T>(SERVER_API_URL, path);
export const clientApi = <T>(path: string) => get<T>(PUBLIC_API_URL, path);

export const formatNumber = (n: number | null | undefined, digits = 0) =>
  n == null
    ? "—"
    : n.toLocaleString("en-GB", {
        maximumFractionDigits: digits,
        minimumFractionDigits: 0,
      });
