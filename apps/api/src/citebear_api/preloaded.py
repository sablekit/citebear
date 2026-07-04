"""The preloaded document library and its attribution (SPEC §11).

The public instance ships a small, license-clean library so a visitor can ask
real questions without uploading anything. Each entry records where to fetch the
original, how to title it, and the attribution the product and README must show
(authors, license, canonical link). This manifest is the single source of truth:
`load_library` ingests from it, and the document endpoints enrich their rows
with the attribution keyed by `source_url`.

Only NC/ND-free works are eligible (SPEC §11): a GPL manual, a dual GPL/CC-BY-SA
handbook, and a US-government public-domain publication.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Attribution:
    """What the UI and README credit for a source document."""

    authors: str
    license_name: str
    license_url: str


@dataclass(frozen=True)
class LibraryDocument:
    """One preloaded document: its canonical original and attribution.

    `source_url` is both the citation link (the original, page-deep-linked with
    `#page=`) and the URL `load_library` fetches the bytes from.
    """

    title: str
    filename: str
    source_url: str
    attribution: Attribution


LIBRARY: list[LibraryDocument] = [
    LibraryDocument(
        title="Calibre User Manual",
        filename="calibre.pdf",
        source_url="https://manual.calibre-ebook.com/calibre.pdf",
        attribution=Attribution(
            authors="Kovid Goyal",
            license_name="GPL-3.0-only",
            license_url="https://www.gnu.org/licenses/gpl-3.0.html",
        ),
    ),
    LibraryDocument(
        title="The Debian Administrator's Handbook",
        filename="debian-handbook.pdf",
        source_url="https://debian-handbook.info/download/buster/debian-handbook.pdf",
        attribution=Attribution(
            authors="Raphaël Hertzog & Roland Mas",
            license_name="GPL-2.0-or-later AND CC-BY-SA-3.0",
            license_url="https://debian-handbook.info/about-the-book/",
        ),
    ),
    LibraryDocument(
        title="NIST SP 800-63B-4: Digital Identity Guidelines",
        filename="NIST.SP.800-63B-4.pdf",
        source_url="https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-63B-4.pdf",
        attribution=Attribution(
            authors="NIST (Temoshok et al.)",
            license_name="Public domain (US Government work)",
            license_url="https://www.nist.gov/open/copyright-fair-use-and-licensing-statements-srd-data-software-and-technical-series-publications",
        ),
    ),
]

_BY_SOURCE_URL: dict[str, LibraryDocument] = {doc.source_url: doc for doc in LIBRARY}


def attribution_for(source_url: str) -> Attribution | None:
    """The attribution for a preloaded document, or None for uploads/self-owned
    docs the library doesn't cover."""
    doc = _BY_SOURCE_URL.get(source_url)
    return doc.attribution if doc else None
