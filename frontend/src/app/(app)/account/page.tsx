import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { SectionLoader } from "@/components/brand";
import { PageHeader, Panel } from "@/components/ui";
import { ROLE_LABEL } from "@/lib/api";
import { currentUser } from "@/lib/server";

import { SignOutEverywhere } from "./SignOutEverywhere";

export const metadata: Metadata = { title: "Account" };

const ROLE_RIGHTS = {
  admin: "Everything, including accounts, datasets and the audit log.",
  researcher: "Read everything; add community claims and review other researchers' claims.",
  company: "Read everything; manage your organisation's solutions in the directory.",
  viewer: "Read only.",
};

export default function AccountPage() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6">
      <PageHeader title="Account" />
      <Suspense fallback={<SectionLoader label="Loading account" />}>
        <Account />
      </Suspense>
    </div>
  );
}

async function Account() {
  const user = await currentUser();
  return (
    <div className="space-y-6">
      <Panel title="Your account">
        <dl className="grid grid-cols-[8rem_1fr] gap-y-2 text-sm">
          <dt className="text-muted">Name</dt>
          <dd>{user.full_name}</dd>
          <dt className="text-muted">E-mail</dt>
          <dd>{user.email}</dd>
          <dt className="text-muted">Role</dt>
          <dd>
            {ROLE_LABEL[user.role]}
            <p className="text-xs text-muted">{ROLE_RIGHTS[user.role]}</p>
          </dd>
          <dt className="text-muted">Last sign-in</dt>
          <dd>{user.last_login_at ? new Date(user.last_login_at).toLocaleString("en-GB") : "—"}</dd>
        </dl>
      </Panel>
      <Panel title="Security">
        <div className="flex flex-wrap items-center gap-3">
          <Link
            href="/account/password"
            className="rounded-md border border-line px-4 py-2 text-sm font-medium hover:border-brand/40"
          >
            Change password
          </Link>
          <SignOutEverywhere />
        </div>
        <p className="mt-3 text-xs text-muted">
          Signing out everywhere ends every session of this account, on every device.
        </p>
      </Panel>
    </div>
  );
}
