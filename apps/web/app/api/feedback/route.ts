import { env } from "@/env";
import { problemResponse } from "@/lib/problem";

/**
 * Feedback proxy: forwards a 👍/👎 to the Python API with the internal key, so
 * the API origin stays private (like the chat proxy). The browser posts
 * `{ messageId, rating }`; the API upserts one row per message.
 */
export async function POST(request: Request): Promise<Response> {
  const body = await request.text();

  let upstream: Response;
  try {
    upstream = await fetch(`${env.API_URL}/feedback`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Internal-Key": env.INTERNAL_API_KEY,
      },
      body,
    });
  } catch {
    return problemResponse(502, "Bad Gateway", "The feedback service is unreachable.");
  }

  return new Response(upstream.status === 204 ? null : await upstream.text(), {
    status: upstream.status,
    headers: {
      "Content-Type": upstream.headers.get("content-type") ?? "application/problem+json",
    },
  });
}
