"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

/** Password gate for /admin (SPEC §7). On success the server sets the httpOnly
 * cookie and we refresh so the server component re-renders as authenticated. */
export function AdminLogin() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const response = await fetch("/api/admin/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      if (response.ok) {
        router.refresh();
        return; // stay busy: the authenticated view replaces this form
      }
      setError("Incorrect password.");
    } catch {
      // a rejected fetch (network drop) must not wedge the form on "…"
      setError("Could not reach the server. Please try again.");
    }
    setBusy(false);
  }

  return (
    <div className="flex flex-1 items-center justify-center px-4">
      <form
        onSubmit={submit}
        className="flex w-full max-w-sm flex-col gap-4 rounded-2xl border border-zinc-200 p-6 dark:border-zinc-800"
      >
        <div>
          <h1 className="text-lg font-semibold tracking-tight">🐻 CiteBear admin</h1>
          <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
            Enter the admin password to manage documents.
          </p>
        </div>
        <input
          type="password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          placeholder="Admin password"
          aria-label="Admin password"
          autoFocus
          className="rounded-xl border border-zinc-300 bg-transparent px-4 py-2.5 outline-none transition-colors focus:border-zinc-500 dark:border-zinc-700 dark:focus:border-zinc-400"
        />
        {error && (
          <p role="alert" className="text-sm text-red-600 dark:text-red-400">
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={busy || password === ""}
          className="rounded-xl bg-zinc-900 px-5 py-2.5 font-medium text-zinc-50 transition-opacity disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900"
        >
          {busy ? "…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
