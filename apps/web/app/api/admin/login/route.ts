import { timingSafeEqual } from "node:crypto";
import { cookies } from "next/headers";

import { env } from "@/env";
import { ADMIN_COOKIE } from "@/lib/admin-auth";
import { problemResponse } from "@/lib/problem";

/**
 * Admin login/logout (SPEC §6). Login validates the password server-side and
 * stores it in an httpOnly cookie; the raw password never reaches client JS.
 * Logout clears it.
 */

function correctPassword(candidate: string): boolean {
  const a = Buffer.from(candidate);
  const b = Buffer.from(env.ADMIN_PASSWORD);
  return a.length === b.length && timingSafeEqual(a, b);
}

export async function POST(request: Request): Promise<Response> {
  let password: unknown;
  try {
    ({ password } = (await request.json()) as { password?: unknown });
  } catch {
    password = undefined;
  }
  if (typeof password !== "string" || !correctPassword(password)) {
    return problemResponse(401, "Unauthorized", "Incorrect admin password.");
  }
  (await cookies()).set(ADMIN_COOKIE, password, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 12, // 12h; re-enter the password after that
  });
  return new Response(null, { status: 204 });
}

export async function DELETE(): Promise<Response> {
  (await cookies()).delete(ADMIN_COOKIE);
  return new Response(null, { status: 204 });
}
