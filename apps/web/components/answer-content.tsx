"use client";

import ReactMarkdown, { type Components } from "react-markdown";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import remarkGfm from "remark-gfm";

import type { Citation } from "@/lib/chat-events";
import { rehypeCitations } from "@/lib/rehype-citations";
import { CitationChip } from "./citation-chip";

// Allow the <cite> wrapper the citation plugin adds; everything else stays on
// the default (GitHub) sanitize schema. Model output is never trusted as raw
// HTML — react-markdown ignores it and sanitize enforces the allowlist.
const schema = {
  ...defaultSchema,
  tagNames: [...(defaultSchema.tagNames ?? []), "cite"],
};

function markerFromNode(node: unknown): number | null {
  // node is the hast <cite> element; its only child is the "[n]" text
  const element = node as { children?: Array<{ value?: string }> } | undefined;
  const value = element?.children?.[0]?.value ?? "";
  const match = /\d+/.exec(value);
  return match ? Number(match[0]) : null;
}

/**
 * Renders a streamed answer as sanitized markdown, turning each `[n]` marker
 * into a clickable citation chip. Unknown markers (no matching source) fall back
 * to their plain bracketed text, so a hallucinated `[9]` never becomes a dead
 * chip. Re-parsing on every token keeps partial markdown readable while it
 * streams.
 */
export function AnswerContent({
  text,
  citations,
  onSelect,
}: {
  text: string;
  citations: Map<number, Citation>;
  onSelect: (citation: Citation) => void;
}) {
  const components: Components = {
    a: ({ children, href }) => (
      <a href={href} target="_blank" rel="noopener noreferrer">
        {children}
      </a>
    ),
    cite: ({ node, children }) => {
      const marker = markerFromNode(node);
      const citation = marker != null ? citations.get(marker) : undefined;
      if (!citation) return <span className="not-italic">{children}</span>;
      return <CitationChip citation={citation} onSelect={onSelect} />;
    },
  };

  return (
    <div className="citebear-markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeCitations, [rehypeSanitize, schema]]}
        components={components}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
