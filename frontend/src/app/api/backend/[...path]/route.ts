// Backend-for-frontend: forwards browser requests to the API with the session from the
// httpOnly cookie. Only /api/v1/ paths are forwarded, and never the routes that return a
// session token (those have their own handlers under /api/auth/).
import { NextResponse } from "next/server";

import { API_URL, forwardedFor, sameOrigin, sessionToken } from "@/lib/server";

const BLOCKED = new Set(["api/v1/auth/login", "api/v1/auth/change-password"]);
const PASS_HEADERS = ["content-type", "content-disposition", "cache-control"];

async function forward(request: Request, ctx: RouteContext<"/api/backend/[...path]">) {
  const { path } = await ctx.params;
  const joined = path.join("/");
  if (!joined.startsWith("api/v1/") || BLOCKED.has(joined) || path.some((p) => p === ".." || p === ".")) {
    return NextResponse.json({ detail: "not found" }, { status: 404 });
  }
  if (request.method !== "GET" && !sameOrigin(request)) {
    return NextResponse.json({ detail: "bad origin" }, { status: 403 });
  }
  const token = await sessionToken();
  if (!token) return NextResponse.json({ detail: "sign in required" }, { status: 401 });

  const url = new URL(request.url);
  const headers: Record<string, string> = {
    Authorization: `Bearer ${token}`,
    ...forwardedFor(request),
  };
  const contentType = request.headers.get("content-type");
  if (contentType) headers["Content-Type"] = contentType;

  let res: Response;
  try {
    res = await fetch(`${API_URL}/${joined}${url.search}`, {
      method: request.method,
      headers,
      body: request.method === "GET" || request.method === "HEAD" ? undefined : await request.arrayBuffer(),
      cache: "no-store",
    });
  } catch {
    return NextResponse.json({ detail: "The API is unavailable." }, { status: 503 });
  }
  const out = new NextResponse(res.status === 204 ? null : res.body, { status: res.status });
  for (const h of PASS_HEADERS) {
    const v = res.headers.get(h);
    if (v) out.headers.set(h, v);
  }
  return out;
}

export const GET = forward;
export const POST = forward;
export const PUT = forward;
export const PATCH = forward;
export const DELETE = forward;
