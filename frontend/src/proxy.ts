// Optimistic sign-in check: pages without a session cookie go to the sign-in page.
// The API checks every request properly; this only avoids rendering pages that would fail.
import { type NextRequest, NextResponse } from "next/server";

const PUBLIC = ["/login"];

export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  if (PUBLIC.some((p) => pathname === p || pathname.startsWith(`${p}/`))) return NextResponse.next();
  if (request.cookies.has("ci_session")) return NextResponse.next();
  const login = new URL("/login", request.url);
  if (pathname !== "/") login.searchParams.set("next", pathname + search);
  return NextResponse.redirect(login);
}

export const config = {
  // Pages only: not API routes, Next internals, brand files, map worker or metadata files.
  matcher: ["/((?!api/|_next/|brand/|maplibre/|icon|favicon|robots.txt).*)"],
};
