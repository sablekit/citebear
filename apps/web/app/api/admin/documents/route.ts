import { proxyToAdminApi } from "@/lib/admin-proxy";

/** Admin documents proxy (SPEC §6): list every status, register a new upload. */

export async function GET(): Promise<Response> {
  return proxyToAdminApi("/admin/documents");
}

export async function POST(request: Request): Promise<Response> {
  return proxyToAdminApi("/admin/documents", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: await request.text(),
  });
}
