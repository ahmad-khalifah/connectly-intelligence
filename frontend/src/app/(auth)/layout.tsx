export default function AuthLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="grid min-h-screen lg:grid-cols-[1.05fr_1fr]">
      <aside className="relative hidden overflow-hidden bg-brand text-white lg:flex lg:flex-col lg:justify-between lg:p-12">
        <div aria-hidden className="absolute -right-24 -top-24 h-96 w-96 rounded-full border-[28px] border-white/5" />
        <div aria-hidden className="absolute -bottom-32 -left-20 h-[28rem] w-[28rem] rounded-full border-[28px] border-gold/15" />
        <div className="relative flex items-center gap-3 text-sm tracking-wide text-white/80">
          <span className="h-px w-8 bg-gold" />
          Connectly Intelligence
        </div>
        <div className="relative max-w-md">
          <p className="font-display text-3xl font-semibold leading-snug">
            Evidence about communities, matched to technology that serves them.
          </p>
          <p className="mt-4 text-sm leading-relaxed text-white/75">
            Every figure carries its source, period and how it was produced. Where data does not
            exist, the platform says so.
          </p>
        </div>
        <p className="relative text-xs text-white/60">Healthcare · Education · Agriculture · Finance · Energy · Commerce · Transport · Connectivity</p>
      </aside>
      <main className="flex items-center justify-center px-4 py-12 sm:px-8">
        <div className="w-full max-w-sm">{children}</div>
      </main>
    </div>
  );
}
