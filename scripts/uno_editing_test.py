#!/usr/bin/env python3
"""Editing-behaviour tests: undo grouping, reading order, pasted copies.

Checks that a refresh is a single undo step, that citations inside
tables and footnotes are numbered where the reader meets them rather
than after the whole body, and that a copy/pasted citation becomes an
independent live citation instead of dead text.

Run like uno_smoke.py: soffice headless listening on port 2002.
"""

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT + "/src/python/pythonpath")

import uno  # noqa: E402
from com.sun.star.text.ControlCharacter import PARAGRAPH_BREAK  # noqa: E402


def connect(port, attempts=30):
    local = uno.getComponentContext()
    resolver = local.ServiceManager.createInstanceWithContext(
        "com.sun.star.bridge.UnoUrlResolver", local)
    url = ("uno:socket,host=localhost,port=%d;urp;"
           "StarOffice.ComponentContext" % port)
    for _ in range(attempts):
        try:
            return resolver.resolve(url)
        except Exception:
            time.sleep(1)
    raise SystemExit("could not connect to soffice on port %d" % port)


def check(label, cond):
    print(("PASS  " if cond else "FAIL  ") + label)
    return bool(cond)


def new_doc(desktop):
    return desktop.loadComponentFromURL("private:factory/swriter",
                                        "_blank", 0, ())


def cite_at_end(doc, by_id, key):
    """Insert a citation at the end of the body text."""
    from mlo import document
    text = doc.getText()
    doc.getCurrentController().getViewCursor().gotoRange(text.getEnd(), False)
    document.insert_citation_mark(
        doc, {"items": [{"rec": by_id[key]}]}, "(pending)")


def test_undo_is_one_step(desktop, by_id, records):
    from mlo import document, styles
    doc = new_doc(desktop)
    text = doc.getText()
    ok = True
    text.insertString(text.getEnd(), "Intro ", False)
    cite_at_end(doc, by_id, "smith2020deep")
    text.insertString(text.getEnd(), " and ", False)
    cite_at_end(doc, by_id, "garcia2018stats")
    doc.getCurrentController().getViewCursor().gotoRange(text.getEnd(), False)
    document.insert_bibliography_section(doc)

    document.refresh_document(doc, styles.get_style("ieee"), records)
    before = doc.getText().getString()
    ok &= check("refresh rendered numeric citations", "[1]" in before)

    undo = doc.getUndoManager()
    ok &= check("refresh recorded an undo action",
                undo.isUndoPossible())
    # One Ctrl+Z must undo the entire refresh, not one edit of it.
    undo.undo()
    after = doc.getText().getString()
    ok &= check("single undo reverted the whole refresh",
                "[1]" not in after and "(pending)" in after)
    doc.close(False)
    return ok


def test_reading_order(desktop, by_id, records):
    """A citation in a table, then one in a footnote, then body text."""
    from mlo import document, styles
    doc = new_doc(desktop)
    text = doc.getText()
    ok = True

    # 1) table at the top, citation inside its only cell
    table = doc.createInstance("com.sun.star.text.TextTable")
    table.initialize(1, 1)
    text.insertTextContent(text.getEnd(), table, False)
    cell = table.getCellByName(table.getCellNames()[0])
    vc = doc.getCurrentController().getViewCursor()
    vc.gotoRange(cell.getEnd(), False)
    document.insert_citation_mark(
        doc, {"items": [{"rec": by_id["lee2019chapter"]}]}, "(pending)")

    # 2) a footnote whose text carries a citation
    text.insertControlCharacter(text.getEnd(), PARAGRAPH_BREAK, False)
    text.insertString(text.getEnd(), "Body with a note", False)
    note = doc.createInstance("com.sun.star.text.Footnote")
    text.insertTextContent(text.getEnd(), note, False)
    vc.gotoRange(note.getEnd(), False)
    document.insert_citation_mark(
        doc, {"items": [{"rec": by_id["garcia2018stats"]}]}, "(pending)")

    # 3) plain body citation, last in reading order
    text.insertString(text.getEnd(), " and finally ", False)
    cite_at_end(doc, by_id, "smith2020deep")

    document.refresh_document(doc, styles.get_style("ieee"), records)

    cell_text = table.getCellByName(table.getCellNames()[0]).getString()
    note_text = note.getString()
    body_text = doc.getText().getString()
    ok &= check("table citation numbered [1]", "[1]" in cell_text)
    ok &= check("footnote citation numbered [2]", "[2]" in note_text)
    ok &= check("body citation numbered [3]", "[3]" in body_text)
    doc.close(False)
    return ok


def test_pasted_citation_adopted(desktop, by_id, records):
    from mlo import document, payload, styles
    doc = new_doc(desktop)
    text = doc.getText()
    ok = True
    text.insertString(text.getEnd(), "Original ", False)
    cite_at_end(doc, by_id, "smith2020deep")
    document.refresh_document(doc, styles.get_style("apa"), records)

    # Simulate a paste: LibreOffice gives the duplicate bookmark a
    # numeric suffix, and the copy carries no payload of its own.
    marks = document.get_citation_marks(doc)
    source = marks[0][0].getName()
    source_key = payload.key_from_bookmark(source)
    text.insertString(text.getEnd(), " copy ", False)
    cursor = text.createTextCursorByRange(text.getEnd())
    cursor.setString("(Smith & Jones, 2020)")
    copy = doc.createInstance("com.sun.star.text.Bookmark")
    copy.setName("%s_1" % source)
    text.insertTextContent(cursor, copy, True)

    ok &= check("copy is not live before refresh",
                len(document.get_citation_marks(doc)) == 1)

    n, _ = document.refresh_document(doc, styles.get_style("apa"), records)
    names = [m.getName() for m, _ in document.get_citation_marks(doc)]
    ok &= check("copy adopted as a live citation", n == 2)
    ok &= check("copy got a key of its own",
                len(names) == 2 and len(set(names)) == 2
                and all(payload.key_from_bookmark(x) for x in names))
    ok &= check("original keeps its key", source in names)

    # Both must survive a further refresh with independent payloads.
    n2, _ = document.refresh_document(doc, styles.get_style("ieee"), records)
    body = doc.getText().getString()
    ok &= check("both citations refresh again", n2 == 2)
    ok &= check("both render the same source", body.count("[1]") == 2)
    ok &= check("source key still present",
                payload.key_from_bookmark(source) == source_key)
    doc.close(False)
    return ok


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 2002
    ctx = connect(port)
    desktop = ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.frame.Desktop", ctx)

    from mlo import bibtex

    records = bibtex.parse_bibtex_file(ROOT + "/tests/sample.bib")
    by_id = {r["id"]: r for r in records}

    ok = True
    print("--- undo grouping")
    ok &= test_undo_is_one_step(desktop, by_id, records)
    print("--- reading order")
    ok &= test_reading_order(desktop, by_id, records)
    print("--- pasted citations")
    ok &= test_pasted_citation_adopted(desktop, by_id, records)

    print("EDITING " + ("OK" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
