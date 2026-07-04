import { describe, expect, it } from "vitest";

import { META_DATA_PART, META_PART, SOURCES_DATA_PART, SOURCES_PART, SSE_EVENT } from "./chat-events";

// These constants are the wire contract between the Python API and the chat
// UI (SPEC §5.4). A silent rename on either side would break streaming with no
// type error, so pin the exact strings here.
describe("chat-events wire contract", () => {
  it("names the four SSE events emitted by the API", () => {
    expect(SSE_EVENT).toEqual({
      sources: "sources",
      token: "token",
      done: "done",
      error: "error",
    });
  });

  it("derives the data-part discriminant from the sources part name", () => {
    expect(SOURCES_PART).toBe("sources");
    expect(SOURCES_DATA_PART).toBe("data-sources");
  });

  it("derives the meta data-part from the done event's part name", () => {
    expect(META_PART).toBe("meta");
    expect(META_DATA_PART).toBe("data-meta");
  });
});
