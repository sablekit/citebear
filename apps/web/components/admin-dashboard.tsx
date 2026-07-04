"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { AdminDocuments } from "./admin-documents";
import { AdminQuestions } from "./admin-questions";

/** Authenticated admin shell (SPEC §7): Documents, Questions, and Stats tabs. */

const TABS = ["Documents", "Questions"] as const;
type Tab = (typeof TABS)[number];

export function AdminDashboard() {
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("Documents");

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

      <nav className="flex gap-1 border-b border-zinc-200 dark:border-zinc-800" aria-label="Admin sections">
        {TABS.map((name) => (
          <button
            key={name}
            type="button"
            onClick={() => setTab(name)}
            aria-current={tab === name ? "page" : undefined}
            className={`-mb-px border-b-2 px-3 py-2.5 text-sm font-medium transition-colors ${
              tab === name
                ? "border-zinc-900 text-zinc-900 dark:border-zinc-100 dark:text-zinc-100"
                : "border-transparent text-zinc-500 hover:text-zinc-800 dark:text-zinc-400 dark:hover:text-zinc-200"
            }`}
          >
            {name}
          </button>
        ))}
      </nav>

      <main className="flex flex-1 flex-col py-6">
        {tab === "Documents" && <AdminDocuments />}
        {tab === "Questions" && <AdminQuestions />}
      </main>
    </div>
  );
}
