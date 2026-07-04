"use client";

import { upload } from "@vercel/blob/client";
import { useCallback, useEffect, useRef, useState } from "react";

import { CONTENT_TYPE_BY_EXTENSION } from "@/lib/document-types";

/** Documents tab (SPEC §7): drag-drop upload straight to Blob, then register
 * with the api; a status-polled list with delete. */

interface AdminDocument {
  id: string;
  title: string;
  filename: string;
  mimeType: string;
  sourceUrl: string;
  pageCount: number | null;
  status: "processing" | "ready" | "failed";
  error: string | null;
  createdAt: string;
}

const POLL_MS = 3000; // reflect processing -> ready/failed across reloads

async function fetchDocuments(): Promise<AdminDocument[] | null> {
  const response = await fetch("/api/admin/documents", { cache: "no-store" });
  return response.ok ? ((await response.json()) as AdminDocument[]) : null;
}

function titleFromFilename(filename: string): string {
  return filename.replace(/\.[^.]+$/, "") || filename;
}

const STATUS_STYLE: Record<AdminDocument["status"], string> = {
  processing: "bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300",
  ready: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300",
  failed: "bg-red-100 text-red-800 dark:bg-red-950/60 dark:text-red-300",
};

export function AdminDocuments() {
  const [documents, setDocuments] = useState<AdminDocument[]>([]);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    const docs = await fetchDocuments();
    if (docs) setDocuments(docs);
  }, []);

  // initial load
  useEffect(() => {
    let active = true;
    void (async () => {
      const docs = await fetchDocuments();
      if (active && docs) setDocuments(docs);
    })();
    return () => {
      active = false;
    };
  }, []);

  // poll only while something is still processing, and only when the tab is
  // visible — a settled list in a backgrounded tab must not keep hitting the API
  const hasProcessing = documents.some((document) => document.status === "processing");
  useEffect(() => {
    if (!hasProcessing) return;
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") void refresh();
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [hasProcessing, refresh]);

  const ingest = useCallback(
    async (files: File[]) => {
      setError(null);
      setBusy(true);
      try {
        for (const file of files) {
          const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
          const contentType = CONTENT_TYPE_BY_EXTENSION[ext];
          if (!contentType) {
            setError(`Unsupported file type: ${file.name} (PDF, DOCX, or Markdown only)`);
            continue;
          }
          // straight to Blob (bypasses the 4.5 MB function body limit), then
          // register — the POST holds while the api ingests synchronously
          const blob = await upload(file.name, file, {
            access: "public",
            handleUploadUrl: "/api/admin/blob-upload",
            contentType,
          });
          const response = await fetch("/api/admin/documents", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              blobUrl: blob.url,
              filename: file.name,
              title: titleFromFilename(file.name),
            }),
          });
          if (!response.ok) {
            const problem = (await response.json().catch(() => null)) as { detail?: string } | null;
            setError(problem?.detail ?? `Could not ingest ${file.name}.`);
          }
        }
      } catch {
        setError("Upload failed. Please try again.");
      } finally {
        setBusy(false);
        await refresh(); // one refresh after the batch; the poll takes over if anything is still processing
      }
    },
    [refresh],
  );

  async function remove(document: AdminDocument) {
    if (!confirm(`Delete "${document.title}"? This removes its chunks and citations.`)) return;
    setError(null);
    try {
      const response = await fetch(`/api/admin/documents/${document.id}`, { method: "DELETE" });
      if (!response.ok) setError(`Could not delete ${document.title}.`);
    } catch {
      setError(`Could not delete ${document.title}.`);
    }
    await refresh();
  }

  return (
    <div className="flex flex-col gap-6">
      <div
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragging(false);
          // ignore a drop while a batch is already uploading — overlapping
          // batches clobber each other's error state and can race a re-ingest
          if (!busy) void ingest(Array.from(event.dataTransfer.files));
        }}
        className={`flex flex-col items-center gap-3 rounded-2xl border border-dashed px-6 py-10 text-center transition-colors ${
          dragging
            ? "border-zinc-500 bg-zinc-50 dark:border-zinc-400 dark:bg-zinc-900"
            : "border-zinc-300 dark:border-zinc-700"
        }`}
      >
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          Drag a PDF, DOCX, or Markdown file here, or
        </p>
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={busy}
          className="rounded-xl bg-zinc-900 px-5 py-2.5 font-medium text-zinc-50 transition-opacity disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900"
        >
          {busy ? "Uploading…" : "Choose a file"}
        </button>
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.docx,.md,.markdown"
          multiple
          hidden
          onChange={(event) => {
            if (event.target.files) void ingest(Array.from(event.target.files));
            event.target.value = "";
          }}
        />
        <p className="text-xs text-zinc-400 dark:text-zinc-500">
          Up to 20 MB. Large documents take a minute to process.
        </p>
      </div>

      {error && (
        <p role="alert" className="text-sm text-red-600 dark:text-red-400">
          {error}
        </p>
      )}

      {documents.length === 0 ? (
        <p className="text-sm text-zinc-500 dark:text-zinc-400">No documents yet.</p>
      ) : (
        <ul className="flex flex-col divide-y divide-zinc-200 dark:divide-zinc-800">
          {documents.map((document) => (
            <li key={document.id} className="flex items-center gap-3 py-3">
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">{document.title}</p>
                <p className="truncate text-xs text-zinc-500 dark:text-zinc-400">
                  {document.filename}
                  {document.pageCount !== null && ` · ${document.pageCount} pages`}
                  {document.status === "failed" && document.error && ` · ${document.error}`}
                </p>
              </div>
              <span
                className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium capitalize ${STATUS_STYLE[document.status]}`}
              >
                {document.status}
              </span>
              <button
                type="button"
                onClick={() => void remove(document)}
                className="shrink-0 text-sm text-zinc-500 underline transition-colors hover:text-red-600 dark:text-zinc-400 dark:hover:text-red-400"
              >
                Delete
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
