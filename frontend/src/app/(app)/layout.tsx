import Link from "next/link";
import { Suspense } from "react";

import { Mark, ProductLockup } from "@/components/brand";
import { NavLinks, NavLinksFallback } from "@/components/shell/NavLinks";
import { UserMenu } from "@/components/shell/UserMenu";

export default function AppLayout({ children }: LayoutProps<"/">) {
  return (
    <>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-3 focus:z-50 focus:rounded focus:bg-panel focus:px-3 focus:py-2 focus:shadow"
      >
        Skip to content
      </a>
      <header className="sticky top-0 z-30 border-b border-line bg-panel/95 backdrop-blur">
        <div className="h-[3px] bg-brand" />
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-8 gap-y-2 px-4 pt-3 sm:px-6 lg:flex-nowrap lg:py-3">
          <Link href="/" aria-label="Connectly Intelligence home" className="shrink-0">
            <ProductLockup height={24} priority />
          </Link>
          <div className="ml-auto lg:order-last">
            <Suspense fallback={<div className="h-8 w-28 animate-pulse rounded-full bg-paper" />}>
              <UserMenu />
            </Suspense>
          </div>
          <Suspense fallback={<NavLinksFallback />}>
            <NavLinks />
          </Suspense>
        </div>
      </header>
      <main id="main" className="flex-1">
        {children}
      </main>
      <footer className="border-t border-line bg-panel">
        <div className="mx-auto flex max-w-7xl items-start gap-3 px-4 py-5 text-xs text-muted sm:px-6">
          <Mark size={18} className="mt-0.5 shrink-0" />
          <p>
            Connectly Intelligence reads every figure from its database and shows its source.
            Missing data is reported, never estimated. Boundaries © GRID3, CC BY 4.0, via
            geoBoundaries.{" "}
            <Link href="/data" className="text-brand underline-offset-2 hover:underline">
              Data sources and licences
            </Link>
          </p>
        </div>
      </footer>
    </>
  );
}
