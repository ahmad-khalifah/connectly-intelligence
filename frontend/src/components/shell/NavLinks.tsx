"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export const NAV = [
  { href: "/", label: "Overview" },
  { href: "/explorer", label: "Explorer" },
  { href: "/intelligence", label: "Intelligence" },
  { href: "/needs", label: "Needs" },
  { href: "/matching", label: "Matching" },
  { href: "/market-entry", label: "Market entry" },
  { href: "/directory", label: "Directory" },
  { href: "/data", label: "Data sources" },
];

export function NavLinks() {
  return <NavList pathname={usePathname()} />;
}

/** Rendered before the current path is known (dynamic routes stream it in). */
export function NavLinksFallback() {
  return <NavList pathname={null} />;
}

function NavList({ pathname }: { pathname: string | null }) {
  return (
    <nav aria-label="Main" className="-mx-4 w-[calc(100%+2rem)] overflow-x-auto px-4 lg:mx-0 lg:w-auto lg:px-0">
      <ul className="flex gap-1 text-sm">
        {NAV.map((n) => {
          const active =
            pathname !== null && (n.href === "/" ? pathname === "/" : pathname.startsWith(n.href));
          return (
            <li key={n.href}>
              <Link
                href={n.href}
                aria-current={active ? "page" : undefined}
                className={`relative block whitespace-nowrap px-3 py-2.5 transition-colors lg:py-1.5 ${
                  active ? "font-medium text-brand" : "text-muted hover:text-ink"
                }`}
              >
                {n.label}
                {active && (
                  <span className="absolute inset-x-3 -bottom-px h-0.5 rounded-full bg-gold lg:-bottom-[13px]" />
                )}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
