import { NextResponse } from "next/server";

import { API_URL, SESSION_COOKIE, sameOrigin, sessionToken } from "@/lib/server";

// POST /api/auth/logout            sign out of this browser
// POST /api/auth/logout?all=1      also revoke every other session of this account
export async function POST(request: Request) {
  if (!sameOrigin(request)) return NextResponse.json({ detail: "bad origin" }, { status: 403 });
  const all = new URL(request.url).searchParams.get("all") === "1";
  const token = await sessionToken();
  if (all && token) {
    await fetch(`${API_URL}/api/v1/auth/logout-all`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    }).catch(() => undefined);
  }
  const out = NextResponse.json({ ok: true });
  out.cookies.delete(SESSION_COOKIE);
  return out;
}
