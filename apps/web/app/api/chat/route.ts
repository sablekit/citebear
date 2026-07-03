import {
  createUIMessageStream,
  createUIMessageStreamResponse,
  type UIMessageChunk,
} from "ai";

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

function toUiChunks(events: AsyncGenerator<UpstreamEvent>) {
  return async ({ writer }: { writer: { write: (chunk: UIMessageChunk) => void } }) => {
    const textId = "answer";
    let textStarted = false;
    writer.write({ type: "start" });
    for await (const { event, data } of events) {
      if (event === "token") {
        const { delta } = JSON.parse(data) as { delta: string };
        if (!textStarted) {
          writer.write({ type: "text-start", id: textId });
          textStarted = true;
        }
        writer.write({ type: "text-delta", id: textId, delta });
      } else if (event === "error") {
        const problem = JSON.parse(data) as { title?: string; detail?: string };
        writer.write({
          type: "error",
          errorText: problem.detail ?? problem.title ?? "Something went wrong.",
        });
      }
      // "done" carries messageId/grounded; the feedback UI consumes it in Milestone 5
    }
    if (textStarted) writer.write({ type: "text-end", id: textId });
    writer.write({ type: "finish" });
  };
}

export async function POST(request: Request): Promise<Response> {
  const body = await request.text();
  const forwardedFor = request.headers.get("x-forwarded-for");
  const clientIp = forwardedFor?.split(",")[0]?.trim();

  const upstream = await fetch(`${env.API_URL}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Internal-Key": env.INTERNAL_API_KEY,
      ...(clientIp ? { "X-Client-IP": clientIp } : {}),
    },
    body,
  });

  if (!upstream.ok || !upstream.body) {
    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: {
        "Content-Type": upstream.headers.get("content-type") ?? "application/problem+json",
      },
    });
  }

  const stream = createUIMessageStream({ execute: toUiChunks(parseSse(upstream.body)) });
  return createUIMessageStreamResponse({ stream });
}
