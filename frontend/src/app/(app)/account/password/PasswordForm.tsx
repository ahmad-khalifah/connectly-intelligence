"use client";

import { useState } from "react";

import { hardNavigate } from "@/lib/api";

import { Button, Field, FormMessage, inputClass } from "@/components/forms";

export function PasswordForm() {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const next = String(f.get("new_password"));
    if (next !== f.get("confirm")) {
      setError("The new passwords do not match.");
      return;
    }
    setBusy(true);
    setError(null);
    const res = await fetch("/api/auth/password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ current_password: f.get("current_password"), new_password: next }),
    }).catch(() => null);
    setBusy(false);
    if (!res) return setError("Cannot reach the server.");
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      return setError(String(body.detail ?? "The password could not be changed."));
    }
    hardNavigate("/");
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <Field label="Current password" htmlFor="current_password">
        <input id="current_password" name="current_password" type="password" autoComplete="current-password" required className={inputClass} />
      </Field>
      <Field label="New password" htmlFor="new_password" hint="At least 12 characters. A short phrase is easier to remember.">
        <input id="new_password" name="new_password" type="password" autoComplete="new-password" minLength={12} required className={inputClass} />
      </Field>
      <Field label="Repeat new password" htmlFor="confirm">
        <input id="confirm" name="confirm" type="password" autoComplete="new-password" minLength={12} required className={inputClass} />
      </Field>
      {error && <FormMessage tone="error">{error}</FormMessage>}
      <Button type="submit" busy={busy}>
        Change password
      </Button>
      <p className="text-xs text-muted">Other devices signed in to this account are signed out.</p>
    </form>
  );
}
