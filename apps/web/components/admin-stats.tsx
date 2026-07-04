"use client";

import { useEffect, useState } from "react";

/** Stats tab (SPEC §7): aggregate counters as simple cards, no charting. */

interface Stats {
  totalQuestions: number;
  thumbsUp: number;
  thumbsDown: number;
  refusalRate: number; // 0..1
  documents: number;
}

function Card({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-zinc-200 px-4 py-3 dark:border-zinc-800">
      <p className="text-2xl font-semibold tracking-tight tabular-nums">{value}</p>
      <p className="mt-0.5 text-xs uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
        {label}
      </p>
    </div>
  );
}

export function AdminStats() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const response = await fetch("/api/admin/stats", { cache: "no-store" });
        if (!response.ok) {
          if (active) setError("Could not load stats.");
          return;
        }
        const data = (await response.json()) as Stats;
        if (active) {
          setStats(data);
          setError(null);
        }
      } catch {
        if (active) setError("Could not load stats.");
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  if (error) {
    return (
      <p role="alert" className="text-sm text-red-600 dark:text-red-400">
        {error}
      </p>
    );
  }
  if (!stats) {
    return <p className="text-sm text-zinc-500 dark:text-zinc-400">Loading…</p>;
  }

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
      <Card label="Questions" value={String(stats.totalQuestions)} />
      <Card label="👍 Helpful" value={String(stats.thumbsUp)} />
      <Card label="👎 Not helpful" value={String(stats.thumbsDown)} />
      <Card label="Refusal rate" value={`${Math.round(stats.refusalRate * 100)}%`} />
      <Card label="Documents" value={String(stats.documents)} />
    </div>
  );
}
