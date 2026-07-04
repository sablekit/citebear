import { env } from "@/env";
import { adminApiHeaders } from "@/lib/admin-auth";
import { problemResponse } from "@/lib/problem";

/**
 * Forward an admin request to the Python API, keeping the API origin private
 * (like the chat proxy). Adds the internal key + admin Bearer, rejects a
 * non-admin caller, and relays the upstream status/body verbatim so the API's
 * Problem responses (415/422/404) reach the admin UI unchanged.
 */
export async function proxyToAdminApi(path: string, init?: RequestInit): Promise<Response> {
  const authHeaders = await adminApiHeaders();
  if (!authHeaders) return problemResponse(401, "Unauthorized", "Admin session required.");

  let upstream: Response;
  try {
    upstream = await fetch(`${env.API_URL}${path}`, {
      ...init,
      headers: { ...authHeaders, ...(init?.headers ?? {}) },
      cache: "no-store",
    });
  } catch {
    return problemResponse(502, "Bad Gateway", "The document service is unreachable.");
  }

  const body = await upstream.text();
  return new Response(body.length > 0 ? body : null, {
    status: upstream.status,
    headers: {
      "Content-Type": upstream.headers.get("content-type") ?? "application/json",
    },
  });
}
