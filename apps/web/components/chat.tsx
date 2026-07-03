"use client";

import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport, type UIMessage } from "ai";
import { useState } from "react";

const SUGGESTIONS = [
  "How does hybrid retrieval work?",
  "What happens when the answer isn't in the documents?",
  "How are documents chunked?",
];

function lastUserText(messages: UIMessage[]): string {
  const last = messages.at(-1);
  if (!last || last.role !== "user") return "";
  return last.parts
    .map((part) => (part.type === "text" ? part.text : ""))
    .join("");
}

function messageText(message: UIMessage): string {
  return message.parts
    .map((part) => (part.type === "text" ? part.text : ""))
    .join("");
}

export function Chat() {
  const [sessionId] = useState(() => crypto.randomUUID());
  const [transport] = useState(
    () =>
      new DefaultChatTransport({
        api: "/api/chat",
        prepareSendMessagesRequest: ({ messages }) => ({
          body: { sessionId, message: lastUserText(messages) },
        }),
      }),
  );
  const { messages, sendMessage, status, error, clearError } = useChat({ transport });
  const [input, setInput] = useState("");

  const busy = status === "submitted" || status === "streaming";

  const submit = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || busy) return;
    void sendMessage({ text: trimmed });
    setInput("");
  };

  return (
    <div className="flex flex-1 flex-col items-center">
      <header className="w-full border-b border-zinc-200 dark:border-zinc-800">
        <div className="mx-auto flex w-full max-w-2xl items-baseline gap-3 px-4 py-4">
          <h1 className="text-lg font-semibold tracking-tight">🐻 CiteBear</h1>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">
            Answers cited from the document library — or an honest &ldquo;I don&rsquo;t know.&rdquo;
          </p>
        </div>
      </header>

      <main className="flex w-full max-w-2xl flex-1 flex-col gap-4 px-4 py-6">
        {messages.length === 0 && (
          <div className="flex flex-1 flex-col items-center justify-center gap-6 text-center">
            <p className="text-zinc-500 dark:text-zinc-400">
              Ask about the loaded documents. Every answer sticks to what they actually say.
            </p>
            <ul className="flex flex-col gap-2">
              {SUGGESTIONS.map((suggestion) => (
                <li key={suggestion}>
                  <button
                    type="button"
                    onClick={() => submit(suggestion)}
                    className="rounded-full border border-zinc-300 px-4 py-1.5 text-sm text-zinc-700 transition-colors hover:border-zinc-500 hover:text-zinc-950 dark:border-zinc-700 dark:text-zinc-300 dark:hover:border-zinc-400 dark:hover:text-zinc-50"
                  >
                    {suggestion}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        <ol className="flex flex-col gap-4" aria-live="polite">
          {messages.map((message) => (
            <li
              key={message.id}
              className={
                message.role === "user"
                  ? "self-end rounded-2xl rounded-br-sm bg-zinc-900 px-4 py-2.5 text-zinc-50 dark:bg-zinc-100 dark:text-zinc-900"
                  : "self-start whitespace-pre-wrap rounded-2xl rounded-bl-sm border border-zinc-200 px-4 py-2.5 dark:border-zinc-800"
              }
            >
              {messageText(message)}
            </li>
          ))}
          {status === "submitted" && (
            <li className="self-start px-4 py-2 text-sm text-zinc-400" aria-label="Thinking">
              Retrieving sources…
            </li>
          )}
        </ol>

        {error && (
          <div
            role="alert"
            className="flex items-center justify-between gap-4 rounded-lg border border-red-300 bg-red-50 px-4 py-2.5 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200"
          >
            <span>{error.message || "Something went wrong."}</span>
            <button type="button" onClick={clearError} className="font-medium underline">
              Dismiss
            </button>
          </div>
        )}
      </main>

      <footer className="sticky bottom-0 w-full border-t border-zinc-200 bg-background dark:border-zinc-800">
        <form
          className="mx-auto flex w-full max-w-2xl gap-2 px-4 py-4"
          onSubmit={(event) => {
            event.preventDefault();
            submit(input);
          }}
        >
          <input
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="Ask a question about the documents…"
            aria-label="Your question"
            className="flex-1 rounded-xl border border-zinc-300 bg-transparent px-4 py-2.5 outline-none transition-colors focus:border-zinc-500 dark:border-zinc-700 dark:focus:border-zinc-400"
          />
          <button
            type="submit"
            disabled={busy || input.trim() === ""}
            className="rounded-xl bg-zinc-900 px-5 py-2.5 font-medium text-zinc-50 transition-opacity disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900"
          >
            {busy ? "…" : "Ask"}
          </button>
        </form>
      </footer>
    </div>
  );
}
