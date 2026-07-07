"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { LibraryDocument } from "@/lib/library";

/**
 * The document library and its credits (SPEC §11): a header control opens a
 * slide-over listing every preloaded document with its title, authors, license,
 * and a link to the canonical original — so a visitor can see what CiteBear can
 * answer from, and each source's attribution, without reading the repo.
 * Keyboard-operable (Escape closes, focus returns to the trigger).
 */
export function SourceLibrary({ documents }: { documents: LibraryDocument[] }) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  // close returns keyboard focus to the trigger, so a keyboard user isn't
  // dropped at the top of the document after dismissing the panel. Stable
  // identity keeps the keydown effect from re-subscribing on every render.
  const close = useCallback(() => {
    setOpen(false);
    triggerRef.current?.focus();
  }, []);

  useEffect(() => {
    if (!open) return;
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, close]);

  // nothing to credit (e.g. the api is unreachable) — no empty affordance
  if (documents.length === 0) return null;

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen(true)}
        className="ml-auto self-center rounded-full border border-zinc-300 px-3 py-1 text-sm text-zinc-600 transition-colors hover:border-zinc-500 hover:text-zinc-900 dark:border-zinc-700 dark:text-zinc-300 dark:hover:border-zinc-400 dark:hover:text-zinc-50"
      >
        Library
      </button>

      {open && (
        <>
          <button
            type="button"
            aria-hidden="true"
            tabIndex={-1}
            onClick={close}
            className="fixed inset-0 z-40 cursor-default bg-black/20 dark:bg-black/40"
          />
          <aside
            role="dialog"
            aria-modal="true"
            aria-label="Document library"
            className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l border-zinc-200 bg-background shadow-xl dark:border-zinc-800"
          >
            <header className="flex items-start justify-between gap-4 border-b border-zinc-200 px-5 py-4 dark:border-zinc-800">
              <div>
                <h2 className="text-sm font-semibold">Document library</h2>
                <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">
                  Every answer is cited from these sources.
                </p>
              </div>
              <button
                ref={closeRef}
                type="button"
                onClick={close}
                aria-label="Close library"
                className="-mr-1 rounded-md p-1 text-zinc-500 transition-colors hover:bg-zinc-100 hover:text-zinc-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-zinc-400 dark:hover:bg-zinc-800 dark:hover:text-zinc-100"
              >
                <svg viewBox="0 0 20 20" fill="none" className="h-5 w-5" aria-hidden="true">
                  <path d="M5 5l10 10M15 5L5 15" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
              </button>
            </header>

            <ul className="flex-1 divide-y divide-zinc-200 overflow-y-auto dark:divide-zinc-800">
              {documents.map((doc) => (
                <li key={doc.id} className="px-5 py-4">
                  <a
                    href={doc.sourceUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm font-medium text-amber-700 hover:underline dark:text-amber-400"
                  >
                    {doc.title}
                  </a>
                  {doc.attribution && (
                    <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
                      {doc.attribution.authors} ·{" "}
                      <a
                        href={doc.attribution.licenseUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="hover:underline"
                      >
                        {doc.attribution.licenseName}
                      </a>
                    </p>
                  )}
                </li>
              ))}
            </ul>
          </aside>
        </>
      )}
    </>
  );
}
