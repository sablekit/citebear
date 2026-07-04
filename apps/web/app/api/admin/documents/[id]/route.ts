import { proxyToAdminApi } from "@/lib/admin-proxy";

/** Delete a document (SPEC §6): cascade chunks + Blob original, handled by the api. */
export async function DELETE(
  _request: Request,
  { params }: { params: Promise<{ id: string }> },
): Promise<Response> {
  const { id } = await params;
  return proxyToAdminApi(`/admin/documents/${encodeURIComponent(id)}`, { method: "DELETE" });
}
