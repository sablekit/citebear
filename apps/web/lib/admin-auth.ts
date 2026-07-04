import { timingSafeEqual } from "node:crypto";
import { cookies } from "next/headers";

import { env } from "@/env";

/**
 * Admin session (SPEC §6): after the password is validated once, it lives in an
 * httpOnly cookie the browser can't read. Server-side gates compare against it;
 * the admin API proxy forwards it to the Python API as the Bearer token. The
 * Python API's require_admin is the authoritative check — this is the first gate
 * and the source of the forwarded credential.
 */
export const ADMIN_COOKIE = "admin_session";

/** Constant-time compare of a candidate against the admin password. The single
 * authoritative admin-password check (the login route mints the cookie with it). */
export function matchesAdminPassword(candidate: string): boolean {
  const a = Buffer.from(candidate);
  const b = Buffer.from(env.ADMIN_PASSWORD);
  return a.length === b.length && timingSafeEqual(a, b);
}

/** The admin password from a valid session cookie, or null. */
async function sessionPassword(): Promise<string | null> {
  const cookie = (await cookies()).get(ADMIN_COOKIE)?.value;
  return cookie !== undefined && matchesAdminPassword(cookie) ? cookie : null;
}

export async function isAdmin(): Promise<boolean> {
  return (await sessionPassword()) !== null;
}

/**
 * Headers for forwarding an admin request to the Python API, or null when the
 * caller is not an authenticated admin: the internal-key + Bearer pair every
 * admin hop needs.
 */
export async function adminApiHeaders(): Promise<Record<string, string> | null> {
  const password = await sessionPassword();
  if (password === null) return null;
  return {
    "X-Internal-Key": env.INTERNAL_API_KEY,
    Authorization: `Bearer ${password}`,
  };
}
