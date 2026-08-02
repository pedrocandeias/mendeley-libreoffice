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

Word's bibliography is a *block-level* content control wrapping one
paragraph per entry, and LibreOffice's .docx import flattens it: the
control ends up spanning the first entry only, with every other entry
left in the document as ordinary paragraphs (an already-emptied control
loses all of them). Converting the control alone would therefore leave
the old entries sitting under the freshly generated bibliography, so
the leftovers are swept away too — recognised by the title or DOI of a
work the document actually cites.

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


# ------------------------------------------------- leftover bibliography

# How many unrecognised paragraphs may sit between two recognised
# entries before the old list is taken to have ended. Real reference
# lists do contain entries this extension cannot recognise — a work
# whose citation was deleted from the text, or one added to the list by
# hand — so the sweep has to step over them rather than stop dead. Blank
# paragraphs are not counted; an alphabetical list easily puts half a
# dozen uncited works in a row (three OpenSCAD manuals, two Molenbroek
# standards), while the prose after a reference list never contains
# recognisable entries at all, so anything from 6 upwards cleans real
# documents identically.
SWEEP_GAP = 8

_PUNCTUATION = {"‘": "'", "’": "'", "“": '"', "”": '"',
                "–": "-", "—": "-", " ": " "}
_MIN_TITLE = 15                       # shorter titles match too loosely
_MIN_DOI = 8


def normalise(text: str) -> str:
    """Lowercase, unify typographic punctuation, collapse whitespace."""
    out = (text or "").lower()
    for fancy, plain in _PUNCTUATION.items():
        out = out.replace(fancy, plain)
    return " ".join(out.split())


def entry_fingerprints(clusters) -> set:
    """Title/DOI strings identifying the works cited in `clusters`.

    Only long-enough fragments are kept: a leftover entry is deleted on
    the strength of one of these matching, so they have to be specific
    enough that ordinary prose cannot contain them by accident.
    """
    prints = set()
    for cluster in clusters or []:
        for item in (cluster or {}).get("items", []):
            rec = item.get("rec") or {}
            title = normalise(rec.get("title"))
            if len(title) >= _MIN_TITLE:
                prints.add(title)
            doi = normalise(rec.get("doi"))
            if len(doi) >= _MIN_DOI:
                prints.add(doi)
    return prints


def looks_like_entry(text: str, prints) -> bool:
    """True if `text` reads as a bibliography entry for a cited work."""
    normalised = normalise(text)
    if not normalised:
        return False
    return any(p in normalised for p in prints)


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


def _paragraphs(text):
    """Every paragraph of `text`, in document order."""
    out = []
    try:
        enum = text.createEnumeration()
    except Exception:
        return out
    while enum.hasMoreElements():
        element = enum.nextElement()
        try:
            if element.supportsService("com.sun.star.text.Paragraph"):
                out.append(element)
        except Exception:
            continue
    return out


def _paragraph_index(text, paragraphs, anchor):
    """Index of the paragraph holding `anchor`, or None."""
    for i, para in enumerate(paragraphs):
        try:
            if (text.compareRegionStarts(para, anchor) >= 0
                    and text.compareRegionEnds(para, anchor) <= 0):
                return i
        except Exception:
            continue
    return None


def _remove_paragraph(text, para):
    try:
        text.removeTextContent(para)
        return True
    except Exception:
        # Worst case, leave an empty paragraph rather than stale text.
        try:
            text.createTextCursorByRange(para).setString("")
        except Exception:
            return False
        return True


ENTRY, BLANK, OTHER = "entry", "blank", "other"


def sweep_plan(kinds, gap=SWEEP_GAP):
    """Which of the classified paragraphs after the control to delete.

    `kinds` classifies each paragraph following the bibliography control
    as ENTRY (repeats a cited work), BLANK or OTHER. The old list runs
    from there to the last recognised entry still within `gap`
    unrecognised paragraphs of the previous one; everything after that is
    the document proper. Inside the list, entries and the blanks between
    them go, while unrecognised paragraphs stay — they are references the
    generated bibliography cannot reproduce, and losing them silently
    would be worse than leaving them for the user to deal with.

    Returns (indices to delete, number of paragraphs left inside).
    """
    last_entry = -1
    since_entry = 0
    for i, kind in enumerate(kinds):
        if kind == ENTRY:
            last_entry = i
            since_entry = 0
        elif kind == OTHER:
            since_entry += 1
            if since_entry > gap:
                break
    block = kinds[:last_entry + 1]
    delete = [i for i, kind in enumerate(block) if kind != OTHER]
    return delete, sum(1 for kind in block if kind == OTHER)


def _sweep_leftover_entries(doc, anchor, prints):
    """Delete the old bibliography stranded after the control.

    Returns (paragraphs removed, unrecognised paragraphs left in place).
    """
    if not prints:
        return 0, 0
    text = anchor.getText()
    paragraphs = _paragraphs(text)
    start = _paragraph_index(text, paragraphs, anchor)
    if start is None:
        return 0, 0

    tail = paragraphs[start + 1:]
    kinds = []
    for para in tail:
        try:
            content = para.getString().strip()
        except Exception:
            break
        kinds.append(BLANK if not content
                     else ENTRY if looks_like_entry(content, prints)
                     else OTHER)

    delete, left = sweep_plan(kinds)
    removed = 0
    for i in delete:
        if _remove_paragraph(text, tail[i]):
            removed += 1
    return removed, left


def convert_document(doc):
    """Convert every Mendeley Cite (Word) citation in the document.

    Returns (clusters converted, bibliography converted?, paragraphs of
    the old Word bibliography removed, unrecognised paragraphs left
    inside it).
    """
    from . import document

    try:
        controls_access = doc.getContentControls()
    except Exception:
        raise RuntimeError(
            "This version of LibreOffice does not expose content "
            "controls (LibreOffice 7.4 or newer is required).")

    citations = []
    bibliographies = []
    for i in range(controls_access.getCount()):
        cc = controls_access.getByIndex(i)
        tag = getattr(cc, "Tag", "") or ""
        if tag == BIB_TAG:
            bibliographies.append(cc)
            continue
        if not tag.startswith(TAG_PREFIX):
            continue
        cluster = citation_to_cluster(decode_tag(tag))
        if cluster is not None:
            citations.append((cc, cluster))

    for cc, cluster in citations:
        text, cursor = _dissolve_control(doc, cc, cc.getAnchor().getString())
        key = payload.new_key()
        mark = doc.createInstance("com.sun.star.text.Bookmark")
        mark.setName(payload.bookmark_name(key))
        text.insertTextContent(cursor, mark, True)
        document._write_payload(doc, key, payload.encode(cluster))

    # Citations first: the sweep recognises leftover entries by the works
    # the document cites, which only the converted citations reveal.
    prints = entry_fingerprints(cluster for _, cluster in citations)
    removed = 0
    left = 0
    bib_converted = False
    for cc in bibliographies:
        text, cursor = _dissolve_control(doc, cc, cc.getAnchor().getString())
        anchor = cursor
        if not bib_converted:
            # A document has one bibliography; should Word ever leave a
            # second control behind, only the first becomes the live
            # bibliography (bookmark names are unique) — the rest are
            # dissolved and swept like any other stale entries.
            mark = doc.createInstance("com.sun.star.text.Bookmark")
            mark.setName(payload.BIB_BOOKMARK)
            text.insertTextContent(cursor, mark, True)
            anchor = mark.getAnchor()
            bib_converted = True
        swept, stayed = _sweep_leftover_entries(doc, anchor, prints)
        removed += swept
        left += stayed

    return len(citations), bib_converted, removed, left
