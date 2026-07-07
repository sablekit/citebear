"use client";

import { useEffect, useRef } from "react";

import type { Citation } from "@/lib/chat-events";
import type { Attribution } from "@/lib/library";

/** The `#page=` anchor only means anything for PDFs; other links stay canonical. */
function sourceHref(citation: Citation): string {
  if (citation.page != null && /\.pdf(?:[?#]|$)/i.test(citation.sourceUrl)) {
    return `${citation.sourceUrl}#page=${citation.page}`;
  }
  return citation.sourceUrl;
}

/**
 * Slide-over showing the passage a citation points to: the cited excerpt is
 * highlighted as the source passage, above its document title, section trail,
 * page, and a link to the original file. Keyboard-operable (Escape closes).
 */
export function SourcePanel({
  citation,
  attribution,
  onClose,
}: {
  citation: Citation | null;
  attribution: Attribution | null;
  onClose: () => void;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);
  // the chip that opened the panel, so keyboard focus returns there on close
  const triggerRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!citation) return;
    triggerRef.current = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [citation, onClose]);

  useEffect(() => {
    if (citation) return;
    triggerRef.current?.focus?.();
    triggerRef.current = null;
  }, [citation]);

  if (!citation) return null;

  const location = [citation.sectionPath.join(" › "), citation.page != null ? `p.${citation.page}` : ""]
    .filter(Boolean)
    .join(" · ");

  return (
    <>
      <button
        type="button"
        aria-hidden="true"
        tabIndex={-1}
        onClick={onClose}
        className="fixed inset-0 z-40 cursor-default bg-black/20 dark:bg-black/40"
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={`Source ${citation.marker}`}
        className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l border-zinc-200 bg-background shadow-xl dark:border-zinc-800"
      >
        <header className="flex items-start justify-between gap-4 border-b border-zinc-200 px-5 py-4 dark:border-zinc-800">
          <div className="min-w-0">
            <p className="text-xs font-medium uppercase tracking-wide text-amber-700 dark:text-amber-400">
              Source {citation.marker}
            </p>
            <h2 className="mt-1 truncate text-sm font-semibold" title={citation.docTitle}>
              {citation.docTitle}
            </h2>
            {location && <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">{location}</p>}
          </div>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            aria-label="Close source panel"
            className="-mr-1 rounded-md p-1 text-zinc-500 transition-colors hover:bg-zinc-100 hover:text-zinc-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
          >
            <svg viewBox="0 0 20 20" fill="none" className="h-5 w-5" aria-hidden="true">
              <path d="M5 5l10 10M15 5L5 15" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-5 py-4">
          <blockquote className="border-l-2 border-amber-400 bg-amber-50 px-4 py-3 text-sm leading-relaxed text-zinc-800 dark:bg-amber-500/10 dark:text-zinc-100">
            {citation.snippet}
          </blockquote>
        </div>

        <footer className="border-t border-zinc-200 px-5 py-4 dark:border-zinc-800">
          {attribution && (
            <p className="mb-2 text-xs text-zinc-500 dark:text-zinc-400">
              {attribution.authors} ·{" "}
              <a
                href={attribution.licenseUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="hover:underline"
              >
                {attribution.licenseName}
              </a>
            </p>
          )}
          <a
            href={sourceHref(citation)}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-sm font-medium text-amber-700 hover:underline dark:text-amber-400"
          >
            Open the original
            <svg viewBox="0 0 20 20" fill="none" className="h-4 w-4" aria-hidden="true">
              <path
                d="M8 4h8v8M16 4l-9 9"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </a>
        </footer>
      </aside>
    </>
  );
}
