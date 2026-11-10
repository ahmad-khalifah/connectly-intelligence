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
