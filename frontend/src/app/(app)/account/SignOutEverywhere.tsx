"use client";

import { useState } from "react";

import { hardNavigate } from "@/lib/api";

import { Button } from "@/components/forms";

export function SignOutEverywhere() {
  const [busy, setBusy] = useState(false);
  return (
    <Button
      variant="danger"
      busy={busy}
      onClick={async () => {
        setBusy(true);
        await fetch("/api/auth/logout?all=1", { method: "POST" });
        hardNavigate("/login");
      }}
    >
      Sign out everywhere
    </Button>
  );
}
