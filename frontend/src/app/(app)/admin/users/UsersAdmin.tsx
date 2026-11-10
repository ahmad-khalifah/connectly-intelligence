"use client";

import { useState } from "react";

import { Button, Field, FormMessage, inputClass } from "@/components/forms";
import { Badge, Panel } from "@/components/ui";
import { ApiError, ROLE_LABEL, type Role, sendJson, type User } from "@/lib/api";

const ROLES: Role[] = ["admin", "researcher", "company", "viewer"];

interface Issued {
  user: User;
  temporary_password: string;
}

export function UsersAdmin({ initial, meId }: { initial: User[]; meId: number }) {
  const [users, setUsers] = useState(initial);
  const [error, setError] = useState<string | null>(null);
  const [issued, setIssued] = useState<Issued | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const replace = (u: User) => setUsers((all) => all.map((x) => (x.id === u.id ? u : x)));

  async function run<T>(key: string, fn: () => Promise<T>): Promise<T | undefined> {
    setBusy(key);
    setError(null);
    try {
      return await fn();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "The change could not be saved.");
    } finally {
      setBusy(null);
    }
  }

  async function create(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const f = new FormData(form);
    const r = await run("create", () =>
      sendJson<Issued>("/api/v1/users", "POST", {
        email: f.get("email"),
        full_name: f.get("full_name"),
        role: f.get("role"),
      }),
    );
    if (r) {
      setUsers((all) => [...all, r.user].sort((a, b) => a.full_name.localeCompare(b.full_name)));
      setIssued(r);
      form.reset();
    }
  }

  return (
    <div className="space-y-6">
      {error && <FormMessage tone="error">{error}</FormMessage>}
      {issued && (
        <div className="rounded-lg border border-gold/50 bg-gold-soft p-4 text-sm" role="status">
          <p>
            Temporary password for <strong>{issued.user.email}</strong>. It is shown only now; give
            it to the person privately. They must change it at first sign-in.
          </p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <code className="rounded border border-line bg-panel px-2 py-1 font-mono text-base">
              {issued.temporary_password}
            </code>
            <Button variant="secondary" onClick={() => navigator.clipboard.writeText(issued.temporary_password)}>
              Copy
            </Button>
            <Button variant="ghost" onClick={() => setIssued(null)}>
              Done
            </Button>
          </div>
        </div>
      )}

      <Panel title="Add an account">
        <form onSubmit={create} className="grid gap-4 md:grid-cols-[1fr_1fr_12rem_auto] md:items-end">
          <Field label="Full name" htmlFor="full_name">
            <input id="full_name" name="full_name" required minLength={2} className={inputClass} />
          </Field>
          <Field label="E-mail" htmlFor="new_email">
            <input id="new_email" name="email" type="email" required className={inputClass} />
          </Field>
          <Field label="Role" htmlFor="role">
            <select id="role" name="role" defaultValue="viewer" className={inputClass}>
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {ROLE_LABEL[r]}
                </option>
              ))}
            </select>
          </Field>
          <Button type="submit" busy={busy === "create"}>
            Create
          </Button>
        </form>
      </Panel>

      <Panel title={`Accounts (${users.length})`}>
        <div className="-mx-4 overflow-x-auto">
          <table className="w-full min-w-[720px] text-sm">
            <thead className="text-left text-xs text-muted">
              <tr>
                <th className="px-4 pb-2 font-normal">Name</th>
                <th className="px-2 pb-2 font-normal">Role</th>
                <th className="px-2 pb-2 font-normal">Status</th>
                <th className="px-2 pb-2 font-normal">Last sign-in</th>
                <th className="px-4 pb-2 text-right font-normal">Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-t border-line align-middle">
                  <td className="px-4 py-2.5">
                    <div className="font-medium">
                      {u.full_name} {u.id === meId && <span className="text-xs text-muted">(you)</span>}
                    </div>
                    <div className="text-xs text-muted">{u.email}</div>
                  </td>
                  <td className="px-2 py-2.5">
                    <label className="sr-only" htmlFor={`role-${u.id}`}>
                      Role for {u.full_name}
                    </label>
                    <select
                      id={`role-${u.id}`}
                      value={u.role}
                      disabled={busy !== null}
                      onChange={async (e) => {
                        const r = await run(`role-${u.id}`, () =>
                          sendJson<User>(`/api/v1/users/${u.id}`, "PATCH", { role: e.target.value }),
                        );
                        if (r) replace(r);
                      }}
                      className="rounded-md border border-line bg-panel px-2 py-1 text-sm"
                    >
                      {ROLES.map((r) => (
                        <option key={r} value={r}>
                          {ROLE_LABEL[r]}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-2 py-2.5">
                    <div className="flex flex-wrap gap-1">
                      <Badge tone={u.is_active ? "good" : "neutral"}>{u.is_active ? "active" : "disabled"}</Badge>
                      {u.must_change_password && <Badge tone="warn">temporary password</Badge>}
                    </div>
                  </td>
                  <td className="px-2 py-2.5 text-xs text-muted">
                    {u.last_login_at ? new Date(u.last_login_at).toLocaleString("en-GB") : "never"}
                  </td>
                  <td className="px-4 py-2.5">
                    <div className="flex justify-end gap-2">
                      <Button
                        variant="secondary"
                        className="px-3 py-1"
                        busy={busy === `reset-${u.id}`}
                        onClick={async () => {
                          if (!confirm(`Issue a new temporary password for ${u.email}? Their current sessions end.`)) return;
                          const r = await run(`reset-${u.id}`, () =>
                            sendJson<Issued>(`/api/v1/users/${u.id}/reset-password`, "POST"),
                          );
                          if (r) {
                            replace(r.user);
                            setIssued(r);
                          }
                        }}
                      >
                        Reset password
                      </Button>
                      <Button
                        variant={u.is_active ? "danger" : "secondary"}
                        className="px-3 py-1"
                        busy={busy === `active-${u.id}`}
                        onClick={async () => {
                          const r = await run(`active-${u.id}`, () =>
                            sendJson<User>(`/api/v1/users/${u.id}`, "PATCH", { is_active: !u.is_active }),
                          );
                          if (r) replace(r);
                        }}
                      >
                        {u.is_active ? "Disable" : "Enable"}
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
