import { AdminDashboard } from "@/components/admin-dashboard";
import { AdminLogin } from "@/components/admin-login";
import { isAdmin } from "@/lib/admin-auth";

/** /admin (SPEC §7): password gate, then the documents dashboard. Reading the
 * cookie opts this route into dynamic rendering, which is correct — it is
 * per-request and never cached. */
export default async function AdminPage() {
  return (await isAdmin()) ? <AdminDashboard /> : <AdminLogin />;
}
