import { createUIMessageStream, createUIMessageStreamResponse } from "ai";

import { env } from "@/env";

/**
 * Streaming proxy: forwards the chat request to the Python API (adding the
 * internal key and the visitor's IP) and adapts its SSE protocol
 * (token / done / error, SPEC §5.4) to the AI SDK UI message stream.
 * The API origin stays private and CORS never enters the picture.
 */

interface UpstreamEvent {
  event: string;
  data: string;
}

async function* parseSse(body: ReadableStream<Uint8Array>): AsyncGenerator<UpstreamEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let eventName = "";
  let dataLines: string[] = [];

  const takeEvent = (): UpstreamEvent | null => {
    if (!eventName && dataLines.length === 0) return null;
    const event = { event: eventName || "message", data: dataLines.join("\n") };
    eventName = "";
    dataLines = [];
    return event;
  };

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let newlineIndex = buffer.indexOf("\n");
    while (newlineIndex !== -1) {
      const line = buffer.slice(0, newlineIndex).replace(/\r$/, "");
      buffer = buffer.slice(newlineIndex + 1);
      if (line === "") {
        const event = takeEvent();
        if (event) yield event;
      } else if (line.startsWith("event:")) {
        eventName = line.slice("event:".length).trim();
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice("data:".length).replace(/^ /, ""));
      }
      newlineIndex = buffer.indexOf("\n");
    }
  }
}

function problemResponse(status: number, title: string, detail: string): Response {
  return Response.json(
    { type: "about:blank", title, status, detail },
    { status, headers: { "Content-Type": "application/problem+json" } },
  );
}

export async function POST(request: Request): Promise<Response> {
  const body = await request.text();
  const forwardedFor = request.headers.get("x-forwarded-for");
  const clientIp = forwardedFor?.split(",")[0]?.trim();

  let upstream: Response;
  try {
    upstream = await fetch(`${env.API_URL}/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Internal-Key": env.INTERNAL_API_KEY,
        ...(clientIp ? { "X-Client-IP": clientIp } : {}),
      },
      body,
      // client disconnect must cancel the upstream stream, or the model
      // keeps generating (and billing) for an answer nobody will see
      signal: request.signal,
    });
  } catch {
    return problemResponse(502, "Bad Gateway", "The answer service is unreachable.");
  }

  if (!upstream.ok || !upstream.body) {
    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: {
        "Content-Type": upstream.headers.get("content-type") ?? "application/problem+json",
      },
    });
  }

  const upstreamBody = upstream.body;
  const stream = createUIMessageStream({
    execute: async ({ writer }) => {
      const textId = "answer";
      let textStarted = false;
      let terminated = false; // saw the protocol's done or error event
      writer.write({ type: "start" });
      for await (const { event, data } of parseSse(upstreamBody)) {
        if (event === "token") {
          const { delta } = JSON.parse(data) as { delta: string };
          if (!textStarted) {
            writer.write({ type: "text-start", id: textId });
            textStarted = true;
          }
          writer.write({ type: "text-delta", id: textId, delta });
        } else if (event === "done") {
          // carries messageId/grounded; the feedback UI consumes it in Milestone 5
          terminated = true;
        } else if (event === "error") {
          const problem = JSON.parse(data) as { title?: string; detail?: string };
          writer.write({
            type: "error",
            errorText: problem.detail ?? problem.title ?? "Something went wrong.",
          });
          terminated = true;
        }
      }
      if (textStarted) writer.write({ type: "text-end", id: textId });
      if (!terminated) {
        // upstream closed mid-answer (timeout, reset): a truncated answer
        // must not render as a complete one
        writer.write({ type: "error", errorText: "The answer was cut off. Please retry." });
      }
      writer.write({ type: "finish" });
    },
  });
  return createUIMessageStreamResponse({ stream });
}
