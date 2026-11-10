import type { Metadata } from "next";
import { Suspense } from "react";

import { SectionLoader } from "@/components/brand";
import { PageHeader } from "@/components/ui";
import type { User } from "@/lib/api";
import { requireRole, serverApi } from "@/lib/server";

import { UsersAdmin } from "./UsersAdmin";

export const metadata: Metadata = { title: "Users" };

export default function UsersPage() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <PageHeader
        title="Users"
        lead="Create accounts and set what each person can do. New accounts get a temporary password that must be changed at first sign-in. Every change is written to the audit log."
      />
      <Suspense fallback={<SectionLoader label="Loading accounts" />}>
        <Users />
      </Suspense>
    </div>
  );
}

async function Users() {
  const me = await requireRole("admin");
  const users = await serverApi<User[]>("/api/v1/users");
  return <UsersAdmin initial={users} meId={me.id} />;
}
