import { NextResponse } from "next/server";

import { errorDetail } from "@/lib/api";
import { API_URL, cookieOptions, forwardedFor, SESSION_COOKIE, sameOrigin } from "@/lib/server";

export async function POST(request: Request) {
  if (!sameOrigin(request)) return NextResponse.json({ detail: "bad origin" }, { status: 403 });
  let body: { email?: unknown; password?: unknown };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "invalid request" }, { status: 400 });
  }
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/v1/auth/login`, {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json", ...forwardedFor(request) },
      body: JSON.stringify({ email: String(body.email ?? ""), password: String(body.password ?? "") }),
    });
  } catch {
    return NextResponse.json({ detail: "The sign-in service is unavailable." }, { status: 503 });
  }
  if (!res.ok) {
    return NextResponse.json({ detail: await errorDetail(res) }, { status: res.status });
  }
  const data = await res.json();
  // The token stays in an httpOnly cookie; the page only gets the account details.
  const out = NextResponse.json({ user: data.user });
  out.cookies.set(SESSION_COOKIE, data.access_token, cookieOptions(new Date(data.expires_at)));
  return out;
}
