import Link from "next/link";

import { Mark } from "@/components/brand";

export default function NotFound() {
  return (
    <div className="mx-auto flex max-w-md flex-col items-center px-4 py-20 text-center">
      <Mark size={44} />
      <h1 className="mt-6 text-xl font-semibold">Not found</h1>
      <p className="mt-2 text-sm text-muted">
        This record does not exist, or your account cannot see it.
      </p>
      <Link href="/" className="mt-6 text-sm font-medium text-brand hover:underline">
        Back to the overview
      </Link>
    </div>
  );
}
