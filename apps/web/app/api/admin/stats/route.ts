import { proxyToAdminApi } from "@/lib/admin-proxy";

/** Admin stats proxy (SPEC §6): aggregate counters for the Stats tab. */
export async function GET(): Promise<Response> {
  return proxyToAdminApi("/admin/stats");
}
