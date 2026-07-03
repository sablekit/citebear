import type { Element, Root, Text } from "hast";
import { SKIP, visit } from "unist-util-visit";

/**
 * Wraps every `[n]` citation marker in the rendered answer in a `<cite>`
 * element, so the markdown renderer can map it to a clickable chip. The marker
 * text is kept as the element's only child; the chip reads the number from it.
 *
 * Runs before rehype-sanitize (which keeps `cite` and its text child), so no
 * raw HTML from the model is ever trusted.
 */
const MARKER = /\[(\d+)\]/g;

// A [n] inside code, a link, or an existing cite is not a citation to wrap:
// code samples and quoted source text routinely contain bracketed integers.
const SKIP_PARENTS = new Set(["cite", "code", "pre", "a"]);

export function rehypeCitations() {
  return (tree: Root): void => {
    visit(tree, "text", (node: Text, index, parent) => {
      if (index === undefined || parent === undefined) return;
      if (parent.type === "element" && SKIP_PARENTS.has(parent.tagName)) return;
      MARKER.lastIndex = 0;
      if (!MARKER.test(node.value)) return;

      const replacements: Array<Text | Element> = [];
      let cursor = 0;
      MARKER.lastIndex = 0;
      for (const match of node.value.matchAll(MARKER)) {
        const start = match.index;
        if (start > cursor) {
          replacements.push({ type: "text", value: node.value.slice(cursor, start) });
        }
        replacements.push({
          type: "element",
          tagName: "cite",
          properties: {},
          children: [{ type: "text", value: match[0] }],
        });
        cursor = start + match[0].length;
      }
      if (cursor < node.value.length) {
        replacements.push({ type: "text", value: node.value.slice(cursor) });
      }

      parent.children.splice(index, 1, ...replacements);
      // resume after the inserted nodes so their text is not revisited
      return [SKIP, index + replacements.length];
    });
  };
}
