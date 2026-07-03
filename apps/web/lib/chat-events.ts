import type { UIMessage } from "ai";

/**
 * The SSE event contract for POST /chat (SPEC §5.4), mirrored from the api's
 * events module (apps/api/src/citebear_api/events.py). Defined once here so the
 * streaming proxy and the chat UI cannot drift on an event name or a payload
 * field — the camelCase boundary is applied on the api side.
 */

/** Event names emitted by the Python API over SSE. */
export const SSE_EVENT = {
  sources: "sources",
  token: "token",
  done: "done",
  error: "error",
} as const;

/** One retrieved chunk offered as a citation. Mirrors events.Citation. */
export interface Citation {
  marker: number;
  chunkId: string;
  docTitle: string;
  page: number | null;
  sectionPath: string[];
  sourceUrl: string;
  snippet: string;
}

export interface SourcesData {
  citations: Citation[];
  confidence: string;
}

/**
 * The `sources` event is surfaced to the client as a `data-sources` part, so
 * each assistant message carries its own citations in `message.parts`.
 */
export const SOURCES_PART = "sources" as const;

/** The typed message the chat works with: text parts + a data-sources part. */
export type CitebearUIMessage = UIMessage<unknown, { sources: SourcesData }>;
