import { cookies } from "next/headers";

import { env } from "@/env";
import { ADMIN_COOKIE } from "@/lib/admin-auth";
import { problemResponse } from "@/lib/problem";

/**
 * Admin login/logout (SPEC §6). Login delegates the password check to the
 * Python API, which throttles failed attempts per IP against a Postgres counter
 * (#56); the web can't rate-limit server-side on its own (no DB). On success the
 * password is stored in an httpOnly cookie so the raw value never reaches client
 * JS. Logout clears it.
 */

export async function POST(request: Request): Promise<Response> {
  let password: unknown;
  try {
    ({ password } = (await request.json()) as { password?: unknown });
  } catch {
    password = undefined;
  }
  if (typeof password !== "string") {
    return problemResponse(401, "Unauthorized", "Incorrect admin password.");
  }

  // trusted-hop client IP so the API can attribute the attempt (see chat proxy)
  const clientIp = request.headers.get("x-real-ip")?.trim() || undefined;

  let upstream: Response;
  try {
    upstream = await fetch(`${env.API_URL}/admin/login`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Internal-Key": env.INTERNAL_API_KEY,
        ...(clientIp ? { "X-Client-IP": clientIp } : {}),
      },
      body: JSON.stringify({ password }),
    });
  } catch {
    return problemResponse(502, "Bad Gateway", "The admin service is unreachable.");
  }

  if (!upstream.ok) {
    // propagate the API's 401 / 429 (with Retry-After) unchanged
    const retryAfter = upstream.headers.get("retry-after");
    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: {
        "Content-Type": upstream.headers.get("content-type") ?? "application/problem+json",
        ...(retryAfter ? { "Retry-After": retryAfter } : {}),
      },
    });
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
