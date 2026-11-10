import type { ButtonHTMLAttributes, ReactNode } from "react";

export const inputClass =
  "block w-full rounded-md border border-line bg-panel px-3 py-2 text-sm text-ink placeholder:text-muted/70 focus:border-brand focus:outline-none focus:ring-2 focus:ring-brand/20 disabled:bg-paper";

export function Field({
  label,
  htmlFor,
  hint,
  children,
}: {
  label: string;
  htmlFor: string;
  hint?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div>
      <label htmlFor={htmlFor} className="mb-1 block text-sm font-medium">
        {label}
      </label>
      {children}
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
    </div>
  );
}

export function Button({
  variant = "primary",
  busy,
  className = "",
  children,
  disabled,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger" | "ghost";
  busy?: boolean;
}) {
  const styles = {
    primary: "bg-brand text-white hover:bg-brand-strong",
    secondary: "border border-line bg-panel text-ink hover:border-brand/40",
    danger: "border border-bad/30 bg-panel text-bad hover:bg-bad-soft",
    ghost: "text-brand hover:bg-brand-soft",
  }[variant];
  return (
    <button
      {...rest}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      className={`inline-flex items-center justify-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-60 ${styles} ${className}`}
    >
      {busy && <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-r-transparent" />}
      {children}
    </button>
  );
}

export function FormMessage({ tone, children }: { tone: "error" | "success"; children: ReactNode }) {
  return (
    <p
      role={tone === "error" ? "alert" : "status"}
      className={`rounded-md px-3 py-2 text-sm ${tone === "error" ? "bg-bad-soft text-bad" : "bg-good-soft text-good"}`}
    >
      {children}
    </p>
  );
}

export function CheckboxGroup({
  legend,
  name,
  options,
  value,
  onChange,
  columns = 2,
  hint,
}: {
  legend: string;
  name: string;
  options: Record<string, string>;
  value: string[];
  onChange: (v: string[]) => void;
  columns?: 1 | 2 | 3;
  hint?: ReactNode;
}) {
  const cols = { 1: "", 2: "sm:grid-cols-2", 3: "sm:grid-cols-2 lg:grid-cols-3" }[columns];
  return (
    <fieldset>
      <legend className="mb-1 text-sm font-medium">{legend}</legend>
      {hint && <p className="mb-2 text-xs text-muted">{hint}</p>}
      <div className={`grid gap-x-4 gap-y-1.5 ${cols}`}>
        {Object.entries(options).map(([code, text]) => (
          <label key={code} className="flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              name={name}
              value={code}
              checked={value.includes(code)}
              onChange={(e) =>
                onChange(e.target.checked ? [...value, code] : value.filter((v) => v !== code))
              }
              className="mt-0.5 h-4 w-4 accent-[var(--color-brand)]"
            />
            <span>{text}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

/** A select whose empty option means "not known" (sent as null). */
export function UnknownSelect({
  id,
  label,
  options,
  value,
  onChange,
  hint,
}: {
  id: string;
  label: string;
  options: Record<string, string>;
  value: string | null;
  onChange: (v: string | null) => void;
  hint?: ReactNode;
}) {
  return (
    <Field label={label} htmlFor={id} hint={hint}>
      <select
        id={id}
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value || null)}
        className={inputClass}
      >
        <option value="">Not known</option>
        {Object.entries(options).map(([code, text]) => (
          <option key={code} value={code}>
            {text}
          </option>
        ))}
      </select>
    </Field>
  );
}

export function FormSection({
  title,
  description,
  children,
}: {
  title: string;
  description?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="grid gap-4 border-t border-line pt-6 first:border-t-0 first:pt-0 lg:grid-cols-[14rem_1fr]">
      <div>
        <h2 className="text-sm font-semibold">{title}</h2>
        {description && <p className="mt-1 text-xs text-muted">{description}</p>}
      </div>
      <div className="space-y-4">{children}</div>
    </section>
  );
}
