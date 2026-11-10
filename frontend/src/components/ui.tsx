import type { DatasetRef, Notice } from "@/lib/api";

export function PageHeader({ title, lead }: { title: string; lead?: React.ReactNode }) {
  return (
    <div className="mb-6">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      {lead && <p className="mt-1 max-w-3xl text-sm text-muted">{lead}</p>}
    </div>
  );
}

export function Panel({
  title,
  children,
  aside,
}: {
  title?: string;
  children: React.ReactNode;
  aside?: React.ReactNode;
}) {
  return (
    <section className="rounded-lg border border-line bg-panel">
      {title && (
        <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
          <h2 className="text-sm font-semibold">{title}</h2>
          {aside}
        </div>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function Stat({
  label,
  value,
  note,
}: {
  label: string;
  value: React.ReactNode;
  note?: string;
}) {
  return (
    <div className="rounded-lg border border-line bg-panel px-4 py-3">
      <div className="text-xs text-muted">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
      {note && <div className="mt-0.5 text-xs text-muted">{note}</div>}
    </div>
  );
}

export function NoticeBox({ notice }: { notice: Notice }) {
  return (
    <div className="rounded-md border border-warn/30 bg-warn-soft px-3 py-2 text-sm">
      <div className="font-medium text-warn">{notice.title}</div>
      <p className="mt-0.5 text-ink/80">{notice.description}</p>
    </div>
  );
}

export function Badge({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: "neutral" | "good" | "warn";
}) {
  const cls = {
    neutral: "bg-paper text-muted border-line",
    good: "bg-brand-soft text-brand border-brand/20",
    warn: "bg-warn-soft text-warn border-warn/30",
  }[tone];
  return (
    <span className={`inline-flex items-center rounded border px-1.5 py-0.5 text-xs ${cls}`}>
      {children}
    </span>
  );
}

export function Provenance({ dataset }: { dataset: DatasetRef }) {
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
      <dt className="text-muted">Source</dt>
      <dd>{dataset.source_name}</dd>
      {dataset.distributor && (
        <>
          <dt className="text-muted">Distributed by</dt>
          <dd>{dataset.distributor}</dd>
        </>
      )}
      <dt className="text-muted">Dataset</dt>
      <dd>{dataset.title}</dd>
      {dataset.version && (
        <>
          <dt className="text-muted">Version</dt>
          <dd>{dataset.version}</dd>
        </>
      )}
      <dt className="text-muted">Licence</dt>
      <dd className="flex flex-wrap items-center gap-1.5">
        {dataset.licence ?? "Unknown"}
        <Badge tone={dataset.licence_verified ? "good" : "warn"}>
          {dataset.licence_verified ? "verified" : "not verified"}
        </Badge>
      </dd>
    </dl>
  );
}

export function ErrorBox({ message }: { message: string }) {
  return (
    <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">
      {message}
    </div>
  );
}
