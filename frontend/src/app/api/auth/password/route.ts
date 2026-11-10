import { NextResponse } from "next/server";

import { errorDetail } from "@/lib/api";
import { API_URL, cookieOptions, SESSION_COOKIE, sameOrigin, sessionToken } from "@/lib/server";

export async function POST(request: Request) {
  if (!sameOrigin(request)) return NextResponse.json({ detail: "bad origin" }, { status: 403 });
  const token = await sessionToken();
  if (!token) return NextResponse.json({ detail: "sign in required" }, { status: 401 });
  const res = await fetch(`${API_URL}/api/v1/auth/change-password`, {
    method: "POST",
    cache: "no-store",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body: await request.text(),
  }).catch(() => null);
  if (!res) return NextResponse.json({ detail: "The service is unavailable." }, { status: 503 });
  if (!res.ok) return NextResponse.json({ detail: await errorDetail(res) }, { status: res.status });
  const data = await res.json();
  // Changing the password revokes old sessions, so store the new one.
  const out = NextResponse.json({ user: data.user });
  out.cookies.set(SESSION_COOKIE, data.access_token, cookieOptions(new Date(data.expires_at)));
  return out;
}
