"""Writer document integration (UNO).

Citations are stored as reference marks whose name carries the cluster
payload:

    MLO_CITE 1 <8-hex-uuid> <base64url(zlib(json))>

The payload embeds a full snapshot of each cited record, so documents
stay refreshable even without the library at hand (like the CSL_CITATION
fields Mendeley Cite writes in Word). The bibliography lives in a text
section named MLO_BIBLIOGRAPHY.
"""

import base64
import json
import uuid
import zlib

import uno  # noqa: F401  (ensures we run inside LibreOffice)
from com.sun.star.text.ControlCharacter import PARAGRAPH_BREAK

MARK_PREFIX = "MLO_CITE 1 "
BIB_SECTION = "MLO_BIBLIOGRAPHY"
BIB_PLACEHOLDER = "The bibliography will appear here — use Mendeley > Refresh."


# ---------------------------------------------------------------- payload

def encode_cluster(cluster):
    raw = json.dumps(cluster, ensure_ascii=False,
                     separators=(",", ":")).encode("utf-8")
    payload = base64.urlsafe_b64encode(zlib.compress(raw, 9)).decode("ascii")
    return MARK_PREFIX + uuid.uuid4().hex[:8] + " " + payload


def decode_cluster(name):
    if not name.startswith(MARK_PREFIX):
        return None
    try:
        payload = name[len(MARK_PREFIX):].split(" ", 1)[1]
        raw = zlib.decompress(base64.urlsafe_b64decode(payload.encode("ascii")))
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


# ---------------------------------------------------------------- marks

def _view_cursor_text_cursor(doc):
    vc = doc.getCurrentController().getViewCursor()
    return vc.getText().createTextCursorByRange(vc)


def insert_citation_mark(doc, cluster, rendered_text):
    """Insert a citation cluster at the current selection."""
    cursor = _view_cursor_text_cursor(doc)
    cursor.setString(rendered_text)
    mark = doc.createInstance("com.sun.star.text.ReferenceMark")
    mark.setName(encode_cluster(cluster))
    cursor.getText().insertTextContent(cursor, mark, True)


def get_citation_marks(doc):
    """Return [(mark, cluster)] in document order (best effort)."""
    marks = doc.getReferenceMarks()
    found = []
    for name in marks.getElementNames():
        cluster = decode_cluster(name)
        if cluster is not None:
            found.append((marks.getByName(name), cluster))

    ordered = _order_by_enumeration(doc, found)
    return ordered if ordered is not None else found


def _order_by_enumeration(doc, found):
    """Order marks by enumerating body paragraphs/portions."""
    try:
        by_name = dict((m.getName(), (m, c)) for m, c in found)
        ordered = []
        para_enum = doc.getText().createEnumeration()
        while para_enum.hasMoreElements():
            para = para_enum.nextElement()
            if not para.supportsService("com.sun.star.text.Paragraph"):
                continue
            portions = para.createEnumeration()
            while portions.hasMoreElements():
                portion = portions.nextElement()
                try:
                    if portion.TextPortionType != "ReferenceMark":
                        continue
                    if not portion.IsStart:
                        continue
                    name = portion.ReferenceMark.getName()
                except Exception:
                    continue
                if name in by_name:
                    ordered.append(by_name.pop(name))
        ordered.extend(by_name.values())   # footnote/frame marks at the end
        return ordered
    except Exception:
        return None


def replace_mark(doc, mark, cluster, new_text):
    """Replace a citation mark's text (and refresh its payload)."""
    anchor = mark.getAnchor()
    text = anchor.getText()
    cursor = text.createTextCursorByRange(anchor)
    old_uuid_part = mark.getName()[len(MARK_PREFIX):].split(" ", 1)[0]
    text.removeTextContent(mark)
    cursor.setString(new_text)
    new_mark = doc.createInstance("com.sun.star.text.ReferenceMark")
    raw = json.dumps(cluster, ensure_ascii=False,
                     separators=(",", ":")).encode("utf-8")
    payload = base64.urlsafe_b64encode(zlib.compress(raw, 9)).decode("ascii")
    new_mark.setName(MARK_PREFIX + old_uuid_part + " " + payload)
    text.insertTextContent(cursor, new_mark, True)


# ---------------------------------------------------------------- bibliography

def has_bibliography(doc):
    return doc.getTextSections().hasByName(BIB_SECTION)


def insert_bibliography_section(doc):
    """Insert an (empty) bibliography section at the current selection."""
    if has_bibliography(doc):
        raise RuntimeError("A bibliography already exists in this document. "
                           "Use Mendeley > Refresh to update it.")
    cursor = _view_cursor_text_cursor(doc)
    cursor.setString("")
    text = cursor.getText()
    # New paragraph to host the section, with placeholder content.
    text.insertControlCharacter(cursor, PARAGRAPH_BREAK, False)
    cursor.setString(BIB_PLACEHOLDER)
    section = doc.createInstance("com.sun.star.text.TextSection")
    section.setName(BIB_SECTION)
    text.insertTextContent(cursor, section, True)


def update_bibliography(doc, entries):
    if not has_bibliography(doc):
        return False
    section = doc.getTextSections().getByName(BIB_SECTION)
    anchor = section.getAnchor()
    text = anchor.getText()
    cursor = text.createTextCursorByRange(anchor)
    cursor.setString(entries[0] if entries else "")
    cursor.collapseToEnd()
    for entry in entries[1:]:
        text.insertControlCharacter(cursor, PARAGRAPH_BREAK, False)
        text.insertString(cursor, entry, False)
    # Hanging-indent look via the built-in style, when available.
    try:
        full = text.createTextCursorByRange(section.getAnchor())
        full.setPropertyValue("ParaStyleName", "Bibliography 1")
    except Exception:
        pass
    return True


# ---------------------------------------------------------------- refresh

def refresh_document(doc, style, library_records=None):
    """Re-render all citations and the bibliography.

    library_records, when given, override the snapshots stored in the
    marks (so edits in Mendeley propagate into the document).
    """
    from . import engine
    lib = dict((r["id"], r) for r in (library_records or []))
    marks = get_citation_marks(doc)
    clusters = []
    for mark, cluster in marks:
        for it in cluster.get("items", []):
            rid = it.get("rec", {}).get("id")
            if rid in lib:
                it["rec"] = lib[rid]
        clusters.append(cluster)
    rendered, entries = engine.process(clusters, style)
    for (mark, cluster), text in zip(marks, rendered):
        try:
            replace_mark(doc, mark, cluster, text)
        except Exception:
            continue
    updated_bib = update_bibliography(doc, entries)
    return len(marks), updated_bib
