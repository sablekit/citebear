import type { Element, Root, Text } from "hast";
import { describe, expect, it } from "vitest";

import { rehypeCitations } from "./rehype-citations";

const text = (value: string): Text => ({ type: "text", value });

const el = (tagName: string, ...children: Array<Element | Text>): Element => ({
  type: "element",
  tagName,
  properties: {},
  children,
});

const root = (...children: Array<Element | Text>): Root => ({ type: "root", children });

/** Run the transformer in place and return the mutated tree. */
function transform(tree: Root): Root {
  rehypeCitations()(tree);
  return tree;
}

/** Depth-first list of every `<cite>` element's text content. */
function citeTexts(node: Root | Element): string[] {
  const out: string[] = [];
  for (const child of node.children) {
    if (child.type !== "element") continue;
    if (child.tagName === "cite") {
      const first = child.children[0];
      out.push(first?.type === "text" ? first.value : "");
    }
    out.push(...citeTexts(child));
  }
  return out;
}

describe("rehypeCitations", () => {
  it("wraps a single [n] marker in a <cite> element", () => {
    const tree = transform(root(el("p", text("See [1] here."))));
    expect(citeTexts(tree)).toEqual(["[1]"]);
  });

  it("preserves the text before and after the marker", () => {
    const p = transform(root(el("p", text("See [1] here.")))).children[0] as Element;
    expect(p.children.map((c) => (c.type === "text" ? c.value : "cite"))).toEqual([
      "See ",
      "cite",
      " here.",
    ]);
  });

  it("wraps multiple markers in one text node and keeps the text between them", () => {
    const p = transform(root(el("p", text("[1] and [2]")))).children[0] as Element;
    expect(citeTexts(p)).toEqual(["[1]", "[2]"]);
    expect(p.children.map((c) => (c.type === "text" ? c.value : "cite"))).toEqual([
      "cite",
      " and ",
      "cite",
    ]);
  });

  it("wraps adjacent markers with no text between them", () => {
    const p = transform(root(el("p", text("[1][2]")))).children[0] as Element;
    expect(citeTexts(p)).toEqual(["[1]", "[2]"]);
    expect(p.children.every((c) => c.type === "element")).toBe(true);
  });

  it("wraps multi-digit markers", () => {
    expect(citeTexts(transform(root(el("p", text("ref [10]")))))).toEqual(["[10]"]);
  });

  it("leaves text without a marker untouched", () => {
    const p = transform(root(el("p", text("no markers here")))).children[0] as Element;
    expect(p.children).toEqual([text("no markers here")]);
  });

  it.each(["code", "pre", "a", "cite"])("does not wrap a marker inside <%s>", (tag) => {
    // the marker text stays a single, unmodified text child — no cite inserted
    const parent = transform(root(el(tag, text("value[1]")))).children[0] as Element;
    expect(parent.children).toEqual([text("value[1]")]);
  });

  it("chips a marker in prose but not its sibling inside <code>", () => {
    const tree = transform(root(el("p", text("see [1]"), el("code", text("arr[2]")))));
    expect(citeTexts(tree)).toEqual(["[1]"]);
  });
});
