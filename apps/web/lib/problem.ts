/**
 * RFC 9457 Problem Details (SPEC §6): the web app speaks the same error shape
 * as the Python API, so a proxied error and a locally-generated one look alike.
 */
export function problemResponse(status: number, title: string, detail: string): Response {
  return Response.json(
    { type: "about:blank", title, status, detail },
    { status, headers: { "Content-Type": "application/problem+json" } },
  );
}
