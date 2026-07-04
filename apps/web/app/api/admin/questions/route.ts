import { proxyToAdminApi } from "@/lib/admin-proxy";

/** Admin question-log proxy (SPEC §6): paginated log with grounded + feedback.
 * limit/offset ride through as query params. */
export async function GET(request: Request): Promise<Response> {
  const { search } = new URL(request.url);
  return proxyToAdminApi(`/admin/questions${search}`);
}
