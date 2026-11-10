import type { Metadata } from "next";

import { Logo } from "@/components/brand";

import { LoginForm } from "./LoginForm";

export const metadata: Metadata = { title: "Sign in" };

export default function LoginPage() {
  return (
    <>
      <Logo height={34} priority />
      <h1 className="mt-10 text-2xl font-semibold tracking-tight">Sign in</h1>
      <p className="mt-1 text-sm text-muted">
        Accounts are created by your Connectly administrator.
      </p>
      <LoginForm />
    </>
  );
}
