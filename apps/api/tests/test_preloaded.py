"""Preloaded library manifest: attribution lookup + entry sanity (SPEC §11)."""

from citebear_api.preloaded import LIBRARY, attribution_for


def test_attribution_for_known_source_url() -> None:
    calibre = next(doc for doc in LIBRARY if doc.title == "Calibre User Manual")
    attribution = attribution_for(calibre.source_url)
    assert attribution is not None
    assert attribution.license_name == "GPL-3.0-only"
    assert attribution.authors == "Kovid Goyal"


def test_attribution_for_unknown_source_url_is_none() -> None:
    # uploads and self-owned docs aren't in the manifest; they get no attribution
    assert attribution_for("https://example.test/some-upload.pdf") is None


def test_library_entries_are_complete_and_unique() -> None:
    urls = [doc.source_url for doc in LIBRARY]
    assert len(urls) == len(set(urls)), "source_url is the manifest key; must be unique"
    for doc in LIBRARY:
        assert doc.title and doc.filename and doc.source_url
        assert doc.attribution.authors and doc.attribution.license_name
        assert doc.attribution.license_url.startswith("https://")
