"use client";

import { useRouter } from "next/navigation";

import { AdminDocuments } from "./admin-documents";

/** Authenticated admin shell (SPEC §7). v1 has one tab — Documents; the
 * question log and stats tabs arrive in Milestone 5. */
export function AdminDashboard() {
  const router = useRouter();

  async function logout() {
    try {
      await fetch("/api/admin/login", { method: "DELETE" });
    } catch {
      // a rejected fetch shouldn't throw uncaught; refresh re-gates on the cookie
    }
    router.refresh();
  }

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col px-4">
      <header className="flex items-baseline justify-between border-b border-zinc-200 py-4 dark:border-zinc-800">
        <h1 className="text-lg font-semibold tracking-tight">🐻 CiteBear admin</h1>
        <button
          type="button"
          onClick={logout}
          className="text-sm text-zinc-500 underline transition-colors hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
        >
          Log out
        </button>
      </header>
      <main className="flex flex-1 flex-col py-6">
        <AdminDocuments />
      </main>
    </div>
  );
}
