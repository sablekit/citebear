import type { Attribution } from "@/lib/library";

/**
 * The credit line for a preloaded source (SPEC §11): authors · license, with
 * the license linking to its text. Shared by the citation panel footer and the
 * library list so the two attribution surfaces can't drift on format. The
 * caller supplies the surrounding text styling.
 */
export function AttributionCredit({ attribution }: { attribution: Attribution }) {
  return (
    <>
      {attribution.authors} ·{" "}
      <a
        href={attribution.licenseUrl}
        target="_blank"
        rel="noopener noreferrer"
        className="hover:underline"
      >
        {attribution.licenseName}
      </a>
    </>
  );
}
