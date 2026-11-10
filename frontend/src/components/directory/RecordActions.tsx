"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button, FormMessage, inputClass } from "@/components/forms";
import { ApiError, sendJson } from "@/lib/api";

export interface Action {
  key: string;
  label: string;
  path: string;
  body: Record<string, unknown>;
  needsNote?: "required" | "optional";
  noteLabel?: string;
  variant?: "primary" | "secondary" | "danger";
}

/** Buttons for status and review actions. Actions that need a note open a small form. */
export function RecordActions({ actions }: { actions: Action[] }) {
  const router = useRouter();
  const [open, setOpen] = useState<Action | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(a: Action, withNote?: string) {
    setBusy(a.key);
    setError(null);
    try {
      await sendJson(a.path, "POST", withNote ? { ...a.body, note: withNote } : a.body);
      setOpen(null);
      setNote("");
      router.refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The change could not be saved.");
    } finally {
      setBusy(null);
    }
  }

  if (actions.length === 0) return null;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {actions.map((a) => (
          <Button
            key={a.key}
            variant={a.variant ?? "secondary"}
            busy={busy === a.key}
            onClick={() => (a.needsNote ? setOpen(a) : run(a))}
          >
            {a.label}
          </Button>
        ))}
      </div>
      {open && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            run(open, note.trim() || undefined);
          }}
          className="space-y-2 rounded-md border border-line bg-paper p-3"
        >
          <label htmlFor="action-note" className="block text-sm font-medium">
            {open.noteLabel ?? "Note"} {open.needsNote === "optional" && <span className="font-normal text-muted">(optional)</span>}
          </label>
          <textarea
            id="action-note"
            rows={3}
            required={open.needsNote === "required"}
            minLength={open.needsNote === "required" ? 5 : undefined}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            className={inputClass}
          />
          <div className="flex gap-2">
            <Button type="submit" busy={busy === open.key}>
              {open.label}
            </Button>
            <Button type="button" variant="ghost" onClick={() => setOpen(null)}>
              Cancel
            </Button>
          </div>
        </form>
      )}
      {error && <FormMessage tone="error">{error}</FormMessage>}
    </div>
  );
}
