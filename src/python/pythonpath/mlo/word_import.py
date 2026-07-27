"""Import Mendeley Cite (Word) citations into this extension's format.

Documents managed by the Mendeley Cite add-in for Microsoft Word store
each citation in a content control whose Tag carries the complete state
as base64:

    MENDELEY_CITATION_v3_<base64(json)>

The JSON holds the citationItems, each with the full CSL record of the
cited work (itemData) plus locator/prefix/suffix. The bibliography
lives in a content control tagged MENDELEY_BIBLIOGRAPHY.

This module converts those content controls into the extension's native
format — `MLO_C_<key>` bookmarks with payloads in document properties,
and the `MLO_BIBLIOGRAPHY` bookmark — so the document becomes
manageable in LibreOffice. The conversion is one-way: the Word add-in
no longer recognises the converted citations.

The pure functions (tag decoding and CSL-to-record mapping) do not
depend on UNO and are testable outside LibreOffice.
"""

from __future__ import annotations

import base64
import json

from . import payload

TAG_PREFIX = "MENDELEY_CITATION_v3_"
BIB_TAG = "MENDELEY_BIBLIOGRAPHY"

_KNOWN_TYPES = {"article-journal", "book", "chapter", "paper-conference",
                "thesis", "report", "webpage"}
_TYPE_ALIASES = {
    "article": "article-journal",
    "article-magazine": "article-journal",
    "article-newspaper": "article-journal",
    "conference-paper": "paper-conference",
    "book-section": "chapter",
    "post-weblog": "webpage",
    "web-page": "webpage",
}


# ---------------------------------------------------------------- pure

def decode_tag(tag: str):
    """Decode a citation content control's Tag; None if it is not ours."""
    if not tag or not tag.startswith(TAG_PREFIX):
        return None
    b64 = tag[len(TAG_PREFIX):]
    try:
        raw = base64.b64decode(b64 + "=" * (-len(b64) % 4))
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


def _names(entries) -> list[dict]:
    out = []
    for a in entries or []:
        fam, giv = a.get("family", "") or "", a.get("given", "") or ""
        if fam or giv:
            out.append({"family": fam, "given": giv})
    return out


def csl_to_record(d: dict) -> dict:
    """Convert a CSL-JSON itemData object into an internal record."""
    issued = (d.get("issued") or {}).get("date-parts") or [[]]
    year = issued[0][0] if issued and issued[0] else None
    try:
        year = int(year) if year is not None else None
    except (TypeError, ValueError):
        year = None
    ctype = d.get("type") or ""
    ctype = ctype if ctype in _KNOWN_TYPES else _TYPE_ALIASES.get(ctype,
                                                                  "generic")
    return {
        "id": str(d.get("id") or ""),
        "type": ctype,
        "title": d.get("title", "") or "",
        "authors": _names(d.get("author")),
        "editors": _names(d.get("editor")),
        "year": year,
        "container": d.get("container-title", "")
        or d.get("collection-title", "") or "",
        "volume": str(d.get("volume", "") or ""),
        "issue": str(d.get("issue", "") or ""),
        "pages": str(d.get("page", "") or d.get("page-first", "") or ""),
        "publisher": d.get("publisher", "") or "",
        "place": d.get("publisher-place", "") or "",
        "doi": d.get("DOI", "") or "",
        "url": d.get("URL", "") or "",
        "edition": str(d.get("edition", "") or ""),
    }


def citation_to_cluster(data: dict):
    """Convert a Word citation's JSON into an internal cluster."""
    items = []
    for it in (data or {}).get("citationItems", []):
        rec = csl_to_record(it.get("itemData") or {})
        if not rec["id"] and not rec["title"]:
            continue
        items.append({"rec": rec,
                      "locator": str(it.get("locator", "") or ""),
                      "prefix": it.get("prefix", "") or "",
                      "suffix": it.get("suffix", "") or ""})
    return {"items": items} if items else None


# ---------------------------------------------------------------- UNO

def _dissolve_control(doc, cc, keep_text: str):
    """Remove a content control but keep its text; return a cursor
    spanning that text.

    LibreOffice offers no way to actually delete a content control:
    removeTextContent() empties it but leaves the (now zero-length)
    control behind, and dispose() takes the text with it. So the text is
    moved out of the control and the leftover is stripped of its Tag —
    otherwise it still looks like a Mendeley citation to Word's add-in,
    and a second import would convert it again into a phantom citation
    with no visible text.
    """
    anchor = cc.getAnchor()
    text = anchor.getText()
    cursor = text.createTextCursorByRange(anchor)
    text.removeTextContent(cc)
    if cursor.getString() != keep_text:
        cursor.setString(keep_text)
    try:
        cc.Tag = ""
        cc.Alias = ""
    except Exception:
        pass
    return text, cursor


def convert_document(doc):
    """Convert every Mendeley Cite (Word) citation in the document.

    Returns (number of clusters converted, bibliography converted?).
    """
    from . import document

    try:
        controls_access = doc.getContentControls()
    except Exception:
        raise RuntimeError(
            "This version of LibreOffice does not expose content "
            "controls (LibreOffice 7.4 or newer is required).")

    targets = []
    for i in range(controls_access.getCount()):
        cc = controls_access.getByIndex(i)
        tag = getattr(cc, "Tag", "") or ""
        if tag.startswith(TAG_PREFIX) or tag == BIB_TAG:
            targets.append((tag, cc))

    n_citations = 0
    bib_converted = False
    for tag, cc in targets:
        rendered = cc.getAnchor().getString()
        if tag == BIB_TAG:
            text, cursor = _dissolve_control(doc, cc, rendered)
            mark = doc.createInstance("com.sun.star.text.Bookmark")
            mark.setName(payload.BIB_BOOKMARK)
            text.insertTextContent(cursor, mark, True)
            bib_converted = True
            continue
        cluster = citation_to_cluster(decode_tag(tag))
        if cluster is None:
            continue
        text, cursor = _dissolve_control(doc, cc, rendered)
        key = payload.new_key()
        mark = doc.createInstance("com.sun.star.text.Bookmark")
        mark.setName(payload.bookmark_name(key))
        text.insertTextContent(cursor, mark, True)
        document._write_payload(doc, key, payload.encode(cluster))
        n_citations += 1

    return n_citations, bib_converted
