import { handleUpload, type HandleUploadBody } from "@vercel/blob/client";

import { env } from "@/env";
import { isAdmin } from "@/lib/admin-auth";
import { ALLOWED_CONTENT_TYPES } from "@/lib/document-types";
import { problemResponse } from "@/lib/problem";

/**
 * Mint scoped Blob client-upload tokens (SPEC §5.1). The browser uploads the
 * original straight to Blob — bypassing the 4.5 MB function body limit — after
 * exchanging a token here. Only an authenticated admin can obtain one; the
 * token restricts the upload to supported document types and the 20 MB cap.
 * The api fetches the resulting Blob URL to ingest it.
 */

const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;

export async function POST(request: Request): Promise<Response> {
  const body = (await request.json()) as HandleUploadBody;

  // Only the token-request phase comes from the admin browser; the
  // upload-completed callback comes from Vercel and is verified by handleUpload.
  if (body.type === "blob.generate-client-token" && !(await isAdmin())) {
    return problemResponse(401, "Unauthorized", "Admin session required.");
  }

  try {
    const result = await handleUpload({
      token: env.BLOB_READ_WRITE_TOKEN,
      request,
      body,
      onBeforeGenerateToken: async () => ({
        allowedContentTypes: ALLOWED_CONTENT_TYPES,
        maximumSizeInBytes: MAX_UPLOAD_BYTES,
        addRandomSuffix: true,
      }),
    });
    return Response.json(result);
  } catch {
    return problemResponse(400, "Bad Request", "Could not authorize the upload.");
  }
}
