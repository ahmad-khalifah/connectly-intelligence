"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { hardNavigate } from "@/lib/api";

export function UserMenuClient({
  name,
  email,
  roleLabel,
  isAdmin,
}: {
  name: string;
  email: string;
  roleLabel: string;
  isAdmin: boolean;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const initials = name
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase())
    .join("");

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !ref.current?.contains(e.target as Node))
        setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  async function signOut() {
    await fetch("/api/auth/logout", { method: "POST" });
    hardNavigate("/login");
  }

  const item = "block w-full px-4 py-2 text-left text-sm hover:bg-paper";
  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 rounded-full border border-line py-1 pl-1 pr-3 text-sm hover:border-brand/40"
      >
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-brand text-xs font-semibold text-white">
          {initials}
        </span>
        <span className="hidden max-w-36 truncate sm:inline">{name}</span>
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 z-40 mt-2 w-64 overflow-hidden rounded-lg border border-line bg-panel shadow-lg"
        >
          <div className="border-b border-line px-4 py-3">
            <div className="truncate text-sm font-medium">{name}</div>
            <div className="truncate text-xs text-muted">{email}</div>
            <div className="mt-1 text-xs text-gold-ink">{roleLabel}</div>
          </div>
          <Link role="menuitem" href="/account" className={item} onClick={() => setOpen(false)}>
            Account and password
          </Link>
          {isAdmin && (
            <>
              <Link role="menuitem" href="/admin/users" className={item} onClick={() => setOpen(false)}>
                Users
              </Link>
              <Link role="menuitem" href="/admin/audit" className={item} onClick={() => setOpen(false)}>
                Audit log
              </Link>
            </>
          )}
          <button role="menuitem" type="button" onClick={signOut} className={`${item} border-t border-line text-brand`}>
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
