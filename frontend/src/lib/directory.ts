// Types for the technology solutions directory. Mirror backend/connectly/services/directory.py.

export type Vocab = Record<string, string>;

export interface Vocabularies {
  org_types: Vocab;
  delivery_models: Vocab;
  pricing_models: Vocab;
  internet_requirements: Vocab;
  device_requirements: Vocab;
  power_requirements: Vocab;
  literacy_requirements: Vocab;
  beneficiary_groups: Vocab;
  distribution_channels: Vocab;
  accessibility_features: Vocab;
  partnership_types: Vocab;
  languages: Vocab;
  sectors: { code: string; name: string; needs: { code: string; name: string }[] }[];
}

export type Verification =
  | "unverified"
  | "source_verified"
  | "field_verified"
  | "disputed"
  | "retired";

export const VERIFICATION_LABEL: Record<Verification, string> = {
  unverified: "Not verified",
  source_verified: "Checked against source",
  field_verified: "Verified in the field",
  disputed: "Disputed",
  retired: "Retired",
};

export const verificationTone = (v: string) =>
  v === "source_verified" || v === "field_verified" ? "good" : v === "disputed" ? "bad" : "warn";

export interface Organisation {
  id: number;
  name: string;
  slug: string;
  org_type: string;
  industry: string | null;
  website: string | null;
  description: string | null;
  headquarters: string | null;
  headquarters_country: string;
  headquarters_state_id: number | null;
  headquarters_state: string | null;
  status: "submitted" | "active" | "rejected" | "retired";
  verification_status: Verification;
  verification_note: string | null;
  source_description: string;
  source_url: string | null;
  published_solutions: number;
  created_at: string;
  updated_at: string;
  solutions?: Solution[];
}

export interface Coverage {
  area_id: number;
  name: string;
  level: string;
  kind: "operating" | "expansion_interest";
}

export type SolutionStatus = "draft" | "submitted" | "published" | "rejected" | "retired";

export const STATUS_LABEL: Record<SolutionStatus, string> = {
  draft: "Draft",
  submitted: "Awaiting review",
  published: "Published",
  rejected: "Rejected",
  retired: "Retired",
};

export interface Solution {
  id: number;
  organisation_id: number;
  organisation_name: string;
  organisation_slug: string;
  organisation_status: string;
  organisation_verification: Verification;
  headquarters_country: string;
  name: string;
  sector: string;
  sector_name: string;
  need_codes: string[];
  summary: string;
  description: string | null;
  delivery_model: string | null;
  target_beneficiaries: string | null;
  beneficiary_groups: string[];
  pricing_model: string | null;
  price_min_ngn: number | null;
  price_max_ngn: number | null;
  price_unit: string | null;
  pricing_notes: string | null;
  nationwide: boolean;
  coverage: Coverage[];
  distribution_channels: string[];
  distribution_notes: string | null;
  internet_requirement: string | null;
  device_requirement: string | null;
  power_requirement: string | null;
  literacy_requirement: string | null;
  requirements_notes: string | null;
  languages: string[];
  accessibility_features: string[];
  accessibility_notes: string | null;
  partnership_types: string[];
  partnership_notes: string | null;
  implementation_notes: string | null;
  evidence_of_impact: string | null;
  website: string | null;
  status: SolutionStatus;
  status_note: string | null;
  published_at: string | null;
  verification_status: Verification;
  verification_note: string | null;
  source_description: string;
  source_url: string | null;
  created_by: string | null;
  updated_at: string;
  availability?: Availability | null;
}

export type Availability =
  | "nationwide"
  | "covers_area"
  | "covers_part"
  | "expansion_interest"
  | "not_available"
  | "unknown";

export const AVAILABILITY_LABEL: Record<Availability, string> = {
  nationwide: "Available nationwide",
  covers_area: "Operates here",
  covers_part: "Operates in part of this area",
  expansion_interest: "Plans to expand here",
  not_available: "Not available here",
  unknown: "Coverage not stated",
};

export function formatPrice(s: Pick<Solution, "price_min_ngn" | "price_max_ngn" | "price_unit">) {
  const n = (v: number) => `₦${v.toLocaleString("en-GB")}`;
  if (s.price_min_ngn == null && s.price_max_ngn == null) return null;
  const range =
    s.price_min_ngn != null && s.price_max_ngn != null && s.price_min_ngn !== s.price_max_ngn
      ? `${n(s.price_min_ngn)}–${n(s.price_max_ngn)}`
      : n((s.price_min_ngn ?? s.price_max_ngn) as number);
  return s.price_unit ? `${range} ${s.price_unit}` : range;
}

export const label = (vocab: Vocab, code: string | null | undefined) =>
  code == null ? null : (vocab[code] ?? code);
