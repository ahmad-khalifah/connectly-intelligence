import Link from "next/link";

import { Badge } from "@/components/ui";
import {
  AVAILABILITY_LABEL,
  formatPrice,
  label,
  type Solution,
  STATUS_LABEL,
  type Vocabularies,
  VERIFICATION_LABEL,
  verificationTone,
} from "@/lib/directory";

export function SolutionCard({ s, vocab, showStatus }: { s: Solution; vocab: Vocabularies; showStatus?: boolean }) {
  const price = formatPrice(s);
  return (
    <article className="group relative flex flex-col rounded-lg border border-line bg-panel p-4 transition-colors hover:border-brand/40">
      <div className="flex flex-wrap items-center gap-1.5 text-xs">
        <Badge tone="brand">{s.sector_name}</Badge>
        {showStatus && s.status !== "published" && <Badge tone="warn">{STATUS_LABEL[s.status]}</Badge>}
        <Badge tone={verificationTone(s.verification_status)}>{VERIFICATION_LABEL[s.verification_status]}</Badge>
      </div>
      <h3 className="mt-2 text-base font-semibold">
        <Link href={`/directory/solutions/${s.id}`} className="after:absolute after:inset-0">
          {s.name}
        </Link>
      </h3>
      <p className="text-xs text-muted">{s.organisation_name}</p>
      <p className="mt-2 line-clamp-3 text-sm text-ink/85">{s.summary}</p>
      <dl className="mt-3 grid grid-cols-[6.5rem_1fr] gap-y-1 text-xs">
        <dt className="text-muted">Internet</dt>
        <dd>{label(vocab.internet_requirements, s.internet_requirement) ?? "Not known"}</dd>
        <dt className="text-muted">Device</dt>
        <dd>{label(vocab.device_requirements, s.device_requirement) ?? "Not known"}</dd>
        <dt className="text-muted">Price</dt>
        <dd>{price ?? label(vocab.pricing_models, s.pricing_model) ?? "Not known"}</dd>
        <dt className="text-muted">Languages</dt>
        <dd>{s.languages.length ? s.languages.map((l) => vocab.languages[l] ?? l).join(", ") : "Not known"}</dd>
      </dl>
      {s.availability && (
        <p className={`mt-3 text-xs font-medium ${s.availability === "not_available" ? "text-muted" : s.availability === "unknown" || s.availability === "expansion_interest" ? "text-gold-ink" : "text-good"}`}>
          {AVAILABILITY_LABEL[s.availability]}
        </p>
      )}
    </article>
  );
}
