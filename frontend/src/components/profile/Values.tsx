import { Badge } from "@/components/ui";
import { formatValue, LEVEL_LABEL, type ProfileValue } from "@/lib/api";
import { VALUE_TYPE_LABEL, valueTypeTone } from "@/lib/sectors";

const VERIFIED = new Set(["source_verified", "field_verified"]);

export function ValueBadges({ v }: { v: Pick<ProfileValue, "value_type" | "verification_status"> }) {
  return (
    <span className="inline-flex flex-wrap gap-1">
      <Badge tone={valueTypeTone(v.value_type)}>{VALUE_TYPE_LABEL[v.value_type] ?? v.value_type}</Badge>
      <Badge tone={VERIFIED.has(v.verification_status) ? "good" : v.verification_status === "disputed" ? "bad" : "neutral"}>
        {v.verification_status.replace("_", " ")}
      </Badge>
    </span>
  );
}

/** One sourced value: number, interval, how it was produced and where it comes from. */
export function ValueRow({ v }: { v: ProfileValue }) {
  const interval =
    v.lower_bound != null && v.upper_bound != null
      ? `${formatValue(v.lower_bound, v.unit)} – ${formatValue(v.upper_bound, v.unit)}`
      : null;
  return (
    <li className="py-2.5 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <span className="text-sm">{v.name}</span>
        <span className="text-sm font-semibold tabular-nums">{v.value != null ? formatValue(v.value, v.unit) : (v.value_text ?? "—")}</span>
      </div>
      {interval && <div className="text-right text-xs tabular-nums text-muted">95% interval {interval}</div>}
      <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted">
        {v.is_context && (
          <Badge tone="gold">
            {LEVEL_LABEL[v.measured_at_level]} figure{v.measured_at_area ? `: ${v.measured_at_area}` : ""}
          </Badge>
        )}
        <ValueBadges v={v} />
        <span>{v.period}</span>
        <span>·</span>
        <span title={[v.dataset_title, v.licence, v.attribution].filter(Boolean).join(" · ")}>{v.dataset_title}</span>
      </div>
      {v.is_context && (
        <p className="mt-1 text-xs text-muted">
          Measured for the whole {LEVEL_LABEL[v.measured_at_level].toLowerCase()}; not this area&apos;s own value.
        </p>
      )}
      {v.note && <p className="mt-1 text-xs text-muted">{v.note}</p>}
    </li>
  );
}
