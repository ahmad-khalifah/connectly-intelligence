import type { Metadata } from "next";
import { Suspense } from "react";

import { SectionLoader } from "@/components/brand";
import { PageHeader } from "@/components/ui";
import { currentUser } from "@/lib/server";

import { PasswordForm } from "./PasswordForm";

export const metadata: Metadata = { title: "Change password" };

export default function PasswordPage() {
  return (
    <div className="mx-auto max-w-md px-4 py-8 sm:px-6">
      <PageHeader title="Change password" />
      <Suspense fallback={<SectionLoader label="Loading" />}>
        <Body />
      </Suspense>
    </div>
  );
}

async function Body() {
  const user = await currentUser();
  return (
    <>
      {user.must_change_password && (
        <p className="mb-4 rounded-md border border-gold/40 bg-gold-soft px-3 py-2 text-sm text-gold-ink">
          You signed in with a temporary password. Choose your own to continue.
        </p>
      )}
      <PasswordForm />
    </>
  );
}
