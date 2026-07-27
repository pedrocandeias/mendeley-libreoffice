"""Writer document integration (UNO).

Citations are stored as bookmarks named MLO_C_<8-hex-key> spanning the
rendered citation text; each cluster payload — base64url(zlib(json)),
embedding a full snapshot of the cited records — lives in user-defined
document properties MLO_DATA_<key>_0..n (see payload.py). Bookmarks and
custom document properties survive DOCX round-trips in both LibreOffice
and Microsoft Word, so live citations are preserved regardless of the
file format.

The bibliography is the text spanned by the MLO_BIBLIOGRAPHY bookmark.

Documents written by pre-0.2 versions (reference marks carrying the
payload in their name, bibliography in a text section) are still read,
and each Refresh migrates them to the bookmark format.
"""

import contextlib

import uno  # noqa: F401  (ensures we run inside LibreOffice)
from com.sun.star.awt.FontSlant import ITALIC, NONE
from com.sun.star.beans.PropertyAttribute import REMOVABLE
from com.sun.star.text.ControlCharacter import PARAGRAPH_BREAK

from . import payload

BIB_SECTION = "MLO_BIBLIOGRAPHY"          # pre-0.2 text-section name
BIB_PLACEHOLDER = "The bibliography will appear here — use Mendeley > Refresh."

# Kept for backwards compatibility with external callers/tests.
MARK_PREFIX = payload.LEGACY_MARK_PREFIX

_KIND_BOOKMARK = "bookmark"
_KIND_LEGACY = "legacy"


# ---------------------------------------------------------------- payload

def encode_cluster(cluster):
    """Pre-0.2 helper: full legacy reference-mark name for a cluster."""
    return (payload.LEGACY_MARK_PREFIX + payload.new_key() + " "
            + payload.encode(cluster))


def decode_cluster(name):
    return payload.decode_legacy_mark(name)


# ---------------------------------------------------------------- editing

@contextlib.contextmanager
def batch_edit(doc, title):
    """Group everything done inside into a single undo step.

    A refresh rewrites every citation and the whole bibliography, which
    would otherwise cost the user one Ctrl+Z per edit. Controllers are
    locked for the duration too, so Writer neither redraws nor scrolls
    while the document is being rewritten.

    Undo contexts nest, so it is safe for a caller to wrap a sequence
    that already uses this (the edits merge into the outer step).
    """
    undo = None
    try:
        undo = doc.getUndoManager()
        undo.enterUndoContext(title)
    except Exception:
        undo = None
    try:
        doc.lockControllers()
    except Exception:
        pass
    try:
        yield
    finally:
        try:
            doc.unlockControllers()
        except Exception:
            pass
        if undo is not None:
            try:
                undo.leaveUndoContext()
            except Exception:
                pass


# ---------------------------------------------------------------- properties

def _user_props(doc):
    return doc.getDocumentProperties().getUserDefinedProperties()


def _read_payload(doc, key):
    props = _user_props(doc)
    info = props.getPropertySetInfo()
    parts = []
    n = 0
    while info.hasPropertyByName(payload.prop_name(key, n)):
        parts.append(str(props.getPropertyValue(payload.prop_name(key, n))))
        n += 1
    return "".join(parts) if parts else None


def _remove_payload(doc, key):
    props = _user_props(doc)
    info = props.getPropertySetInfo()
    n = 0
    while info.hasPropertyByName(payload.prop_name(key, n)):
        props.removeProperty(payload.prop_name(key, n))
        n += 1


def _write_payload(doc, key, encoded):
    _remove_payload(doc, key)
    props = _user_props(doc)
    for n, part in enumerate(payload.chunk(encoded)):
        props.addProperty(payload.prop_name(key, n), REMOVABLE, part)


def _gc_payloads(doc, keep_keys):
    """Drop payload properties whose citation no longer exists."""
    props = _user_props(doc)
    stale = set()
    for prop in props.getPropertySetInfo().getProperties():
        key = payload.key_from_prop(prop.Name)
        if key is not None and key not in keep_keys:
            stale.add(key)
    for key in stale:
        try:
            _remove_payload(doc, key)
        except Exception:
            continue


# ---------------------------------------------------------------- marks

def _view_cursor_text_cursor(doc):
    vc = doc.getCurrentController().getViewCursor()
    return vc.getText().createTextCursorByRange(vc)


def insert_citation_mark(doc, cluster, rendered_text):
    """Insert a citation cluster at the current selection."""
    cursor = _view_cursor_text_cursor(doc)
    cursor.setString(rendered_text)
    key = payload.new_key()
    mark = doc.createInstance("com.sun.star.text.Bookmark")
    mark.setName(payload.bookmark_name(key))
    cursor.getText().insertTextContent(cursor, mark, True)
    _write_payload(doc, key, payload.encode(cluster))


def _adopt_copied_citations(doc):
    """Turn pasted citation copies into independent citations.

    A pasted citation arrives as a renamed bookmark ("MLO_C_<key>_1")
    with no payload of its own, so without this it would look live but
    never refresh and never reach the bibliography. Each copy gets a
    fresh key and its own copy of the source payload.

    Copies pasted into a *different* document cannot be recovered — the
    payload lives in document properties, which do not travel with the
    clipboard — so those are left untouched.
    """
    bookmarks = doc.getBookmarks()
    for name in list(bookmarks.getElementNames()):
        source_key = payload.key_from_copied_bookmark(name)
        if source_key is None:
            continue
        encoded = _read_payload(doc, source_key)
        if not encoded:
            continue
        new_key = payload.new_key()
        try:
            _write_payload(doc, new_key, encoded)
            bookmarks.getByName(name).setName(payload.bookmark_name(new_key))
        except Exception:
            _remove_payload(doc, new_key)


def _collect_citations(doc):
    """Return [(kind, mark, key, cluster)] in document order (best effort).

    kind is "bookmark" for the current format (key set) or "legacy" for
    pre-0.2 reference marks (key is None).
    """
    found = []
    bookmarks = doc.getBookmarks()
    for name in bookmarks.getElementNames():
        key = payload.key_from_bookmark(name)
        if key is None:
            continue
        encoded = _read_payload(doc, key)
        cluster = payload.decode(encoded) if encoded else None
        if cluster is not None:
            found.append((_KIND_BOOKMARK, bookmarks.getByName(name),
                          key, cluster))
    refmarks = doc.getReferenceMarks()
    for name in refmarks.getElementNames():
        cluster = payload.decode_legacy_mark(name)
        if cluster is not None:
            found.append((_KIND_LEGACY, refmarks.getByName(name),
                          None, cluster))

    ordered = _order_by_enumeration(doc, found)
    return ordered if ordered is not None else found


def get_citation_marks(doc):
    """Return [(mark, cluster)] in document order (best effort)."""
    return [(mark, cluster)
            for _, mark, _, cluster in _collect_citations(doc)]


def _walk_text(text, by_name, ordered, depth=0):
    """Append citations found in `text`, in reading order.

    Recurses into table cells and into footnotes/endnotes at the point
    where their anchor sits in the text, so a citation inside a table or
    a note numbers according to where the reader meets it rather than
    landing after the whole body.
    """
    if depth > 10:            # pathological nesting guard
        return
    enum = text.createEnumeration()
    while enum.hasMoreElements():
        element = enum.nextElement()
        try:
            if element.supportsService("com.sun.star.text.TextTable"):
                for cell_name in element.getCellNames():
                    _walk_text(element.getCellByName(cell_name),
                               by_name, ordered, depth + 1)
                continue
            if not element.supportsService("com.sun.star.text.Paragraph"):
                continue
        except Exception:
            continue
        portions = element.createEnumeration()
        while portions.hasMoreElements():
            portion = portions.nextElement()
            try:
                ptype = portion.TextPortionType
                if ptype == "Bookmark":
                    if not portion.IsStart:
                        continue
                    name = portion.Bookmark.getName()
                elif ptype == "ReferenceMark":
                    if not portion.IsStart:
                        continue
                    name = portion.ReferenceMark.getName()
                elif ptype == "Footnote":
                    # Footnotes and endnotes both surface here.
                    _walk_text(portion.Footnote, by_name, ordered, depth + 1)
                    continue
                else:
                    continue
            except Exception:
                continue
            entry = by_name.pop(name, None)
            if entry is not None:
                ordered.append(entry)


def _order_by_enumeration(doc, found):
    """Order citations by walking the document in reading order."""
    try:
        by_name = dict((entry[1].getName(), entry) for entry in found)
        ordered = []
        _walk_text(doc.getText(), by_name, ordered)
        # Anything unreachable by the walk (e.g. citations in frames or
        # headers) keeps a stable position at the end.
        ordered.extend(by_name.values())
        return ordered
    except Exception:
        return None


def find_citation_at(doc, text_range):
    """Return (kind, mark, key, cluster) for the citation covering
    text_range, or None.

    Used by Edit Citation to work out which citation the cursor sits in.
    A collapsed cursor touching either edge of the citation counts, so
    clicking just after the closing bracket still finds it.
    """
    for entry in _collect_citations(doc):
        mark = entry[1]
        try:
            anchor = mark.getAnchor()
            text = anchor.getText()
            # Throws when the ranges live in different texts (a footnote
            # versus the body, say), which means it is not this citation.
            starts = text.compareRegionStarts(anchor, text_range)
            ends = text.compareRegionEnds(anchor, text_range)
        except Exception:
            continue
        if starts >= 0 and ends <= 0:
            return entry
    return None


def set_citation_cluster(doc, kind, mark, key, cluster):
    """Store an edited cluster on an existing citation.

    The rendered text is left alone — the caller refreshes afterwards,
    which re-renders every citation anyway. Legacy reference marks are
    migrated to the bookmark format on the way through.
    """
    if kind == _KIND_BOOKMARK and key is not None:
        _write_payload(doc, key, payload.encode(cluster))
        return key
    return _replace_citation(doc, kind, mark, key, cluster,
                             mark.getAnchor().getString())


def _replace_citation(doc, kind, mark, key, cluster, new_text):
    """Replace a citation's text and payload; returns the key in use.

    Legacy reference marks are migrated to the bookmark format here.
    """
    anchor = mark.getAnchor()
    text = anchor.getText()
    cursor = text.createTextCursorByRange(anchor)
    text.removeTextContent(mark)
    cursor.setString(new_text)
    if key is None:
        key = payload.new_key()
    new_mark = doc.createInstance("com.sun.star.text.Bookmark")
    new_mark.setName(payload.bookmark_name(key))
    text.insertTextContent(cursor, new_mark, True)
    _write_payload(doc, key, payload.encode(cluster))
    return key


# ---------------------------------------------------------------- bibliography

def has_bibliography(doc):
    return (doc.getBookmarks().hasByName(payload.BIB_BOOKMARK)
            or doc.getTextSections().hasByName(BIB_SECTION))


def insert_bibliography_section(doc):
    """Insert an (empty) bibliography at the current selection."""
    if has_bibliography(doc):
        raise RuntimeError("A bibliography already exists in this document. "
                           "Use Mendeley > Refresh to update it.")
    cursor = _view_cursor_text_cursor(doc)
    cursor.setString("")
    text = cursor.getText()
    # New paragraph to host the bibliography, with placeholder content.
    text.insertControlCharacter(cursor, PARAGRAPH_BREAK, False)
    cursor.setString(BIB_PLACEHOLDER)
    mark = doc.createInstance("com.sun.star.text.Bookmark")
    mark.setName(payload.BIB_BOOKMARK)
    text.insertTextContent(cursor, mark, True)


def _bib_anchor(doc):
    """Return (container, anchor) for the bibliography, or (None, None).

    container is the bookmark (current format) or the text section
    (pre-0.2 documents), and is consumed by _write_bib_entries.
    """
    bookmarks = doc.getBookmarks()
    if bookmarks.hasByName(payload.BIB_BOOKMARK):
        mark = bookmarks.getByName(payload.BIB_BOOKMARK)
        return mark, mark.getAnchor()
    sections = doc.getTextSections()
    if sections.hasByName(BIB_SECTION):
        section = sections.getByName(BIB_SECTION)
        return section, section.getAnchor()
    return None, None


def _apply_italics(text, entry_start, entry):
    """Italicise the ranges an entry asks for, leaving the rest upright.

    The whole entry is reset to upright first: entries are rewritten in
    place on every refresh, so without that a run could inherit italics
    from whatever occupied those characters last time.
    """
    spans = getattr(entry, "spans", ())
    try:
        whole = text.createTextCursorByRange(entry_start)
        whole.goRight(len(entry), True)
        whole.setPropertyValue("CharPosture", NONE)
        for start, end in spans:
            run = text.createTextCursorByRange(entry_start)
            run.goRight(start, False)
            run.goRight(end - start, True)
            run.setPropertyValue("CharPosture", ITALIC)
    except Exception:
        pass          # formatting is cosmetic; never fail a refresh for it


def update_bibliography(doc, entries):
    container, anchor = _bib_anchor(doc)
    if anchor is None:
        return False
    text = anchor.getText()
    cursor = text.createTextCursorByRange(anchor)
    is_bookmark = container.supportsService("com.sun.star.text.Bookmark")
    if is_bookmark:
        # The bookmark is re-created spanning the new entries below;
        # a text section keeps spanning its content by itself.
        text.removeTextContent(container)
    cursor.setString(entries[0] if entries else "")
    start = text.createTextCursorByRange(cursor.getStart())
    cursor.collapseToEnd()
    if entries:
        _apply_italics(text, start.getStart(), entries[0])
    for entry in entries[1:]:
        text.insertControlCharacter(cursor, PARAGRAPH_BREAK, False)
        entry_start = text.createTextCursorByRange(cursor.getEnd())
        text.insertString(cursor, entry, False)
        _apply_italics(text, entry_start.getStart(), entry)
    span = text.createTextCursorByRange(start.getStart())
    span.gotoRange(cursor.getEnd(), True)
    if is_bookmark:
        mark = doc.createInstance("com.sun.star.text.Bookmark")
        mark.setName(payload.BIB_BOOKMARK)
        text.insertTextContent(span, mark, True)
    # Hanging-indent look via the built-in style, when available.
    try:
        span.setPropertyValue("ParaStyleName", "Bibliography 1")
    except Exception:
        pass
    return True


# ---------------------------------------------------------------- refresh

def refresh_document(doc, style, library_records=None):
    """Re-render all citations and the bibliography.

    library_records, when given, override the snapshots stored in the
    marks (so edits in Mendeley propagate into the document). Legacy
    reference-mark citations are migrated to the bookmark format.
    """
    from . import engine
    lib = dict((r["id"], r) for r in (library_records or []))
    with batch_edit(doc, "Mendeley: refresh citations"):
        _adopt_copied_citations(doc)
        cites = _collect_citations(doc)
        clusters = []
        for _, _, _, cluster in cites:
            for it in cluster.get("items", []):
                rid = it.get("rec", {}).get("id")
                if rid in lib:
                    it["rec"] = lib[rid]
            clusters.append(cluster)
        rendered, entries = engine.process(clusters, style)
        keep_keys = set()
        for (kind, mark, key, cluster), text in zip(cites, rendered):
            try:
                keep_keys.add(_replace_citation(doc, kind, mark, key,
                                                cluster, text))
            except Exception:
                if key is not None:
                    keep_keys.add(key)
                continue
        _gc_payloads(doc, keep_keys)
        updated_bib = update_bibliography(doc, entries)
    return len(cites), updated_bib
