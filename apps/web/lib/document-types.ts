/**
 * The document types CiteBear ingests (SPEC §5.1), keyed by file extension.
 * Single source for the client-side upload gate and the Blob token's allow-list
 * so the two can't drift (a client accepting a type the token would reject).
 * The api independently maps the same extensions in parsing._EXTENSION_MIME.
 */
export const CONTENT_TYPE_BY_EXTENSION: Record<string, string> = {
  pdf: "application/pdf",
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  md: "text/markdown",
  markdown: "text/markdown",
};

export const ALLOWED_CONTENT_TYPES = [...new Set(Object.values(CONTENT_TYPE_BY_EXTENSION))];
