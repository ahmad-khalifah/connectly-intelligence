import Image from "next/image";

// The logo files in /public/brand are the official artwork converted from
// docs/brand/connectly-logo-horizontal.pdf without changes (only the page margin removed).
// Never recolour, stretch or redraw them; always keep the intrinsic aspect ratio.
const LOGO_RATIO = 468 / 85;

export function Logo({ height = 28, priority = false }: { height?: number; priority?: boolean }) {
  return (
    <Image
      src="/brand/connectly-logo-horizontal.svg"
      alt="Connectly"
      width={Math.round(height * LOGO_RATIO)}
      height={height}
      priority={priority}
      unoptimized
    />
  );
}

export function Mark({ size = 32, className }: { size?: number; className?: string }) {
  return (
    <Image
      src="/brand/connectly-mark.svg"
      alt=""
      aria-hidden
      width={size}
      height={size}
      className={className}
      unoptimized
    />
  );
}

/** The Connectly logo with the product name set beside it, separated by a gold rule. */
export function ProductLockup({ height = 26, priority }: { height?: number; priority?: boolean }) {
  return (
    <span className="flex items-center gap-3">
      <Logo height={height} priority={priority} />
      <span aria-hidden className="h-6 w-px bg-gold" />
      <span className="font-display text-[15px] font-medium tracking-wide text-brand">
        Intelligence
      </span>
    </span>
  );
}

/** Full-area loading state: the mark breathing, with a thin progress sweep. */
export function BrandLoader({ label = "Loading" }: { label?: string }) {
  return (
    <div role="status" aria-live="polite" className="flex min-h-[50vh] flex-col items-center justify-center gap-4">
      <Mark size={56} className="animate-brand-pulse" />
      <div className="h-0.5 w-32 overflow-hidden rounded-full bg-line">
        <div className="h-full w-1/3 animate-brand-bar rounded-full bg-gold" />
      </div>
      <span className="text-xs tracking-wide text-muted">{label}…</span>
    </div>
  );
}

/** Inline loading line for sections that stream in. */
export function SectionLoader({ label }: { label: string }) {
  return (
    <div role="status" className="flex items-center gap-3 py-6 text-sm text-muted">
      <Mark size={20} className="animate-brand-pulse" />
      {label}…
    </div>
  );
}
