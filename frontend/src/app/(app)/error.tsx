"use client";

import { Mark } from "@/components/brand";
import { Button } from "@/components/forms";

export default function ErrorPage({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="mx-auto flex max-w-md flex-col items-center px-4 py-20 text-center">
      <Mark size={44} />
      <h1 className="mt-6 text-xl font-semibold">Something went wrong</h1>
      <p className="mt-2 text-sm text-muted">{error.message || "The page could not be loaded."}</p>
      <Button className="mt-6" onClick={reset}>
        Try again
      </Button>
    </div>
  );
}
