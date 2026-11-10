import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Connectly Intelligence",
  description:
    "Community intelligence for technology access in Nigeria. Every value is sourced; missing data is shown, not invented.",
};

const NAV = [
  { href: "/", label: "Overview" },
  { href: "/explorer", label: "Explorer" },
  { href: "/data", label: "Data sources" },
];

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="flex min-h-full flex-col font-sans">
        <header className="border-b border-line bg-panel">
          <div className="mx-auto flex max-w-7xl items-center gap-8 px-4 py-3 sm:px-6">
            <Link href="/" className="flex items-baseline gap-2">
              <span className="text-base font-semibold tracking-tight text-ink">
                Connectly Intelligence
              </span>
              <span className="hidden text-xs text-muted sm:inline">Milestone 1</span>
            </Link>
            <nav className="flex gap-1 text-sm">
              {NAV.map((n) => (
                <Link
                  key={n.href}
                  href={n.href}
                  className="rounded-md px-3 py-1.5 text-muted hover:bg-paper hover:text-ink"
                >
                  {n.label}
                </Link>
              ))}
            </nav>
          </div>
        </header>
        <main className="flex-1">{children}</main>
        <footer className="border-t border-line bg-panel">
          <div className="mx-auto max-w-7xl px-4 py-4 text-xs text-muted sm:px-6">
            Figures on these pages are read directly from the database. Boundaries © GRID3, CC
            BY 4.0, via geoBoundaries. See Data sources for every dataset, licence and gap.
          </div>
        </footer>
      </body>
    </html>
  );
}
