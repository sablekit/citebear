import "server-only";

import { env } from "@/env";

/**
 * The preloaded library's attribution surface (SPEC §11). The api already
 * enriches `GET /documents` with per-document credit from its manifest; the web
 * fetches that list server-side (the endpoint is internal-key gated, never
 * exposed to the browser) so the chat page can credit each source in the
 * citation panel and a library list. Types are safe to `import type` from a
 * client component — the fetch and its server-only env stay on the server.
 */

/** Credit for a preloaded source document; absent for admin uploads. */
export interface Attribution {
  authors: string;
  licenseName: string;
  licenseUrl: string;
}

/** A ready document the chat can cite, as returned by `GET /documents`. */
export interface LibraryDocument {
  id: string;
  title: string;
  sourceUrl: string;
  attribution: Attribution | null;
}

/**
 * The ready document library, or an empty list if the api is unreachable — a
 * missing attribution surface must not blank the chat page.
 */
export async function fetchLibrary(): Promise<LibraryDocument[]> {
  try {
    const response = await fetch(`${env.API_URL}/documents`, {
      headers: { "X-Internal-Key": env.INTERNAL_API_KEY },
      cache: "no-store",
    });
    if (!response.ok) return [];
    return (await response.json()) as LibraryDocument[];
  } catch {
    return [];
  }
}
