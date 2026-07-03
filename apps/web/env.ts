import { createEnv } from "@t3-oss/env-nextjs";
import { z } from "zod";

/**
 * Env-only configuration, validated at build and boot (SPEC §8).
 * Missing config fails the boot, not the request.
 */
export const env = createEnv({
  server: {
    /** Python API origin, e.g. http://localhost:8000 (server-side only). */
    API_URL: z.url(),
    /** Shared secret for the web -> api hop. */
    INTERNAL_API_KEY: z.string().min(1),
  },
  client: {},
  experimental__runtimeEnv: {},
});
