"use client";

import { useEffect, useState } from "react";

/** Questions tab (SPEC §7): paginated question log with grounded + feedback. */

interface QuestionEntry {
  messageId: string;
  question: string;
  answer: string;
  grounded: boolean | null;
  confidence: string | null;
  rating: number | null;
  createdAt: string;
}

interface QuestionPage {
  entries: QuestionEntry[];
  total: number;
  limit: number;
  offset: number;
}

const PAGE_SIZE = 25;

function ratingLabel(rating: number | null): string {
  if (rating === 1) return "👍";
  if (rating === -1) return "👎";
  return "—";
}

export function AdminQuestions() {
  const [page, setPage] = useState<QuestionPage | null>(null);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const response = await fetch(`/api/admin/questions?limit=${PAGE_SIZE}&offset=${offset}`, {
          cache: "no-store",
        });
        if (!response.ok) {
          if (active) setError("Could not load the question log.");
          return;
        }
        const data = (await response.json()) as QuestionPage;
        if (active) {
          setPage(data);
          setError(null);
        }
      } catch {
        if (active) setError("Could not load the question log.");
      }
    })();
    return () => {
      active = false;
    };
  }, [offset]);

  if (error) {
    return (
      <p role="alert" className="text-sm text-red-600 dark:text-red-400">
        {error}
      </p>
    );
  }
  if (!page) {
    return <p className="text-sm text-zinc-500 dark:text-zinc-400">Loading…</p>;
  }
  if (page.total === 0) {
    return <p className="text-sm text-zinc-500 dark:text-zinc-400">No questions yet.</p>;
  }

  // page reflects the last loaded offset; while a newer offset is fetching, the
  // pager is out of sync, so gate the buttons and base the range on the loaded
  // page — otherwise a stale page enables Next past the last page.
  const inFlight = offset !== page.offset;
  const start = page.offset + 1;
  const end = page.offset + page.entries.length;

  return (
    <div className="flex flex-col gap-4">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[40rem] border-collapse text-sm">
          <thead>
            <tr className="border-b border-zinc-200 text-left text-xs uppercase tracking-wide text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
              <th className="py-2 pr-3 font-medium">When</th>
              <th className="py-2 pr-3 font-medium">Question</th>
              <th className="py-2 pr-3 font-medium">Answer</th>
              <th className="py-2 pr-3 font-medium">Status</th>
              <th className="py-2 pr-3 font-medium">Feedback</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-100 dark:divide-zinc-900">
            {page.entries.map((entry) => (
              <tr key={entry.messageId} className="align-top">
                <td className="whitespace-nowrap py-2 pr-3 text-xs text-zinc-500 dark:text-zinc-400">
                  {new Date(entry.createdAt).toLocaleString()}
                </td>
                <td className="max-w-[16rem] py-2 pr-3">
                  <span className="line-clamp-3">{entry.question}</span>
                </td>
                <td className="max-w-[20rem] py-2 pr-3 text-zinc-600 dark:text-zinc-300">
                  <span className="line-clamp-3">{entry.answer}</span>
                </td>
                <td className="whitespace-nowrap py-2 pr-3">
                  {entry.grounded === false ? (
                    <span className="rounded-full bg-red-100 px-2 py-0.5 text-xs font-medium text-red-800 dark:bg-red-950/60 dark:text-red-300">
                      refused
                    </span>
                  ) : (
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                        entry.confidence === "low"
                          ? "bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300"
                          : "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300"
                      }`}
                    >
                      {entry.confidence === "low" ? "low conf." : "grounded"}
                    </span>
                  )}
                </td>
                <td className="whitespace-nowrap py-2 pr-3">{ratingLabel(entry.rating)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between text-sm text-zinc-500 dark:text-zinc-400">
        <span>
          {start}–{end} of {page.total}
        </span>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => setOffset(Math.max(0, page.offset - PAGE_SIZE))}
            disabled={page.offset === 0 || inFlight}
            className="rounded-md border border-zinc-300 px-3 py-1 transition-colors hover:border-zinc-500 disabled:opacity-40 dark:border-zinc-700 dark:hover:border-zinc-400"
          >
            Previous
          </button>
          <button
            type="button"
            onClick={() => setOffset(page.offset + PAGE_SIZE)}
            disabled={end >= page.total || inFlight}
            className="rounded-md border border-zinc-300 px-3 py-1 transition-colors hover:border-zinc-500 disabled:opacity-40 dark:border-zinc-700 dark:hover:border-zinc-400"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}
