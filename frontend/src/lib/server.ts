// Server-only access to the backend API with the signed-in user's session.
import "server-only";

import { cookies } from "next/headers";
import { notFound, redirect } from "next/navigation";

import { ApiError, errorDetail, type User } from "@/lib/api";

export const SESSION_COOKIE = "ci_session";

// Container-to-container address in production; the API's own address in development.
export const API_URL =
  process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function sessionToken(): Promise<string | undefined> {
  return (await cookies()).get(SESSION_COOKIE)?.value;
}

/**
 * GET from the backend as the signed-in user. Redirects to sign-in when the session is
 * missing or expired, and to the password page when a temporary password must be changed.
 */
export async function serverApi<T>(path: string): Promise<T> {
  const token = await sessionToken();
  if (!token) redirect("/login");
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      cache: "no-store",
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch {
    throw new ApiError(0, `Cannot reach the API at ${API_URL}. Is the backend running?`);
  }
  if (res.status === 401) redirect("/login");
  if (res.status === 404) notFound();
  if (!res.ok) {
    const detail = await errorDetail(res);
    if (res.status === 403 && detail.includes("temporary password")) redirect("/account/password");
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

/** The signed-in user (allowed even while a temporary password is pending). */
export async function currentUser(): Promise<User> {
  return serverApi<User>("/api/v1/auth/me");
}

export async function requireRole(...roles: User["role"][]): Promise<User> {
  const user = await currentUser();
  if (!roles.includes(user.role)) redirect("/");
  return user;
}

export function cookieOptions(expires: Date) {
  return {
    httpOnly: true,
    sameSite: "lax" as const,
    // HTTPS-only in production unless explicitly disabled for a local HTTP test.
    secure: process.env.NODE_ENV === "production" && process.env.COOKIE_SECURE !== "false",
    path: "/",
    expires,
  };
}

/** Same-origin check for state-changing requests (defence in depth beside SameSite). */
export function sameOrigin(request: Request): boolean {
  const origin = request.headers.get("origin");
  if (!origin) return false;
  const host = request.headers.get("x-forwarded-host") ?? request.headers.get("host");
  try {
    return new URL(origin).host === host;
  } catch {
    return false;
  }
}

/** Client address to pass on, so the API can rate-limit sign-ins per person, not per server. */
export function forwardedFor(request: Request): Record<string, string> {
  const ip =
    request.headers.get("x-forwarded-for")?.split(",")[0].trim() ??
    request.headers.get("x-real-ip") ??
    undefined;
  return ip ? { "X-Forwarded-For": ip } : {};
}
