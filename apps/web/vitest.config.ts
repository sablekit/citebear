import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    // Every target is a pure function over hast trees or plain data, so the
    // node environment is enough — no jsdom until component tests land (v1).
    environment: "node",
    include: ["lib/**/*.test.ts"],
  },
});
