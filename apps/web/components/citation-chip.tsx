"use client";

import type { Citation } from "@/lib/chat-events";

/**
 * The inline `[n]` marker, rendered as a small clickable pill that opens the
 * source panel. Unknown markers never reach here — the renderer leaves those as
 * plain text (see AnswerContent).
 */
export function CitationChip({
  citation,
  onSelect,
}: {
  citation: Citation;
  onSelect: (citation: Citation) => void;
}) {
  const location = citation.page != null ? `, p.${citation.page}` : "";
  return (
    <button
      type="button"
      onClick={() => onSelect(citation)}
      title={`${citation.docTitle}${location}`}
      aria-label={`Source ${citation.marker}: ${citation.docTitle}`}
      className="mx-0.5 inline-flex h-[1.15em] min-w-[1.15em] items-center justify-center rounded-[0.35em] bg-amber-100 px-1 align-super text-[0.7em] font-medium not-italic leading-none text-amber-800 transition-colors hover:bg-amber-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 dark:bg-amber-500/20 dark:text-amber-300 dark:hover:bg-amber-500/30"
    >
      {citation.marker}
    </button>
  );
}
