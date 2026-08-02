#!/usr/bin/env python3
"""Smoke test for the Mendeley Cite (Word) importer.

Builds content controls in a Writer document identical to the ones the
Word add-in writes (Tag MENDELEY_CITATION_v3_<base64> and
MENDELEY_BIBLIOGRAPHY), runs the conversion, and checks the resulting
bookmarks, payloads and refresh.

Run like uno_smoke.py: soffice headless listening on port 2002.
"""

import base64
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT + "/src/python/pythonpath")

import uno  # noqa: E402


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


def word_tag(citation: dict) -> str:
    return ("MENDELEY_CITATION_v3_"
            + base64.b64encode(json.dumps(citation).encode()).decode())


ITEM_A = {"id": "rec-a", "type": "article-journal",
          "title": "Parametric prosthetic design", "volume": "12",
          "author": [{"family": "Romero", "given": "Elena"}],
          "issued": {"date-parts": [[2025]]},
          "container-title": "IEEE Access", "page": "1-9",
          "DOI": "10.1109/x"}
ITEM_B = {"id": "rec-b", "type": "book-section",
          "title": "Constructive solid geometry",
          "author": [{"family": "Ghali", "given": "Sherif"}],
          "issued": {"date-parts": [[2008]]},
          "container-title": "Introduction to Geometric Computing",
          "publisher": "Springer"}


def any_mendeley_cc(doc):
    """True if any content control still carries a Mendeley Cite tag."""
    from mlo import word_import
    acc = doc.getContentControls()
    for i in range(acc.getCount()):
        tag = getattr(acc.getByIndex(i), "Tag", "") or ""
        if tag.startswith(word_import.TAG_PREFIX) or tag == word_import.BIB_TAG:
            return True
    return False


# The old Word bibliography: one entry inside the content control, the
# others (and a blank separator) stranded after it, then unrelated text
# that the import must leave alone.
BIB_ENTRY_A = ("Ghali, S. (2008). Constructive solid geometry. In "
               "Introduction to Geometric Computing. Springer.")
BIB_ENTRY_B = ("Romero, E. (2025). Parametric prosthetic design. IEEE "
               "Access, 12, 1-9. https://doi.org/10.1109/x")
BIB_ENTRY_C = "Ghali, S. (2008). Constructive solid geometry (reprint)."
UNCITED_ENTRY = "Vitruvius. (30 BCE). De architectura. Rome."
TAIL_TEXT = "Appendix A: interview guide."


def new_para(text):
    text.insertControlCharacter(
        text.getEnd(), uno.getConstantByName(
            "com.sun.star.text.ControlCharacter.PARAGRAPH_BREAK"), False)


def insert_control(doc, text, cursor, rendered, tag):
    cursor.setString(rendered)
    cc = doc.createInstance("com.sun.star.text.ContentControl")
    cc.Tag = tag
    text.insertTextContent(cursor, cc, True)


def run(desktop):
    """Run the scenario against `desktop`; returns True when it passes.

    Split out from main() so it can also be driven from inside a
    LibreOffice that has no reachable UNO socket (see the module
    docstring of scripts/run_uno_tests.sh for the usual path).
    """
    doc = desktop.loadComponentFromURL("private:factory/swriter",
                                       "_blank", 0, ())

    from mlo import document, payload, styles, word_import

    text = doc.getText()
    ok = True

    # citation 1 (single item) and citation 2 (two items, with locator)
    text.insertString(text.getEnd(), "Prosthetics matter ", False)
    cur = text.createTextCursorByRange(text.getEnd())
    insert_control(doc, text, cur, "(Romero, 2025)",
                   word_tag({"citationItems": [
                       {"id": "rec-a", "itemData": ITEM_A}]}))
    text.insertString(text.getEnd(), " and so does geometry ", False)
    cur = text.createTextCursorByRange(text.getEnd())
    insert_control(doc, text, cur, "(Ghali, 2008; Romero, 2025)",
                   word_tag({"citationItems": [
                       {"id": "rec-b", "itemData": ITEM_B, "locator": "281"},
                       {"id": "rec-a", "itemData": ITEM_A}]}))
    text.insertString(text.getEnd(), ".", False)

    # Word bibliography. Word wraps the whole entry list in one
    # block-level content control, but LibreOffice's .docx import leaves
    # the control around the first entry only and drops the rest into
    # the document as plain paragraphs — reproduced here, since those
    # leftovers are what used to survive as a second bibliography.
    new_para(text)
    cur = text.createTextCursorByRange(text.getEnd())
    insert_control(doc, text, cur, BIB_ENTRY_A, "MENDELEY_BIBLIOGRAPHY")
    for para in (BIB_ENTRY_B, "", UNCITED_ENTRY, BIB_ENTRY_C, TAIL_TEXT):
        new_para(text)
        text.insertString(text.getEnd(), para, False)

    ok &= check("2 citation content controls created",
                doc.getContentControls().getCount() == 3)

    n, bib, removed, left = word_import.convert_document(doc)
    ok &= check("2 clusters imported", n == 2)
    ok &= check("bibliography converted", bib)
    ok &= check("stray Word bibliography paragraphs removed", removed == 3)
    ok &= check("uncited entry reported, not deleted", left == 1)
    body_after_import = doc.getText().getString()
    ok &= check("old entries gone from the text",
                BIB_ENTRY_B not in body_after_import
                and BIB_ENTRY_C not in body_after_import)
    ok &= check("uncited entry kept", UNCITED_ENTRY in body_after_import)
    ok &= check("text after the bibliography kept",
                TAIL_TEXT in body_after_import)
    # LibreOffice cannot delete a content control, so the leftovers are
    # emptied and untagged instead; what matters is that nothing still
    # advertises itself as a Mendeley citation.
    ok &= check("no Mendeley content controls left", not any_mendeley_cc(doc))

    marks = document.get_citation_marks(doc)
    ok &= check("2 citation bookmarks", len(marks) == 2)
    ok &= check("locator preserved in payload",
                any(it.get("locator") == "281"
                    for _, c in marks for it in c["items"]))
    ok &= check("bibliography bookmark",
                doc.getBookmarks().hasByName(payload.BIB_BOOKMARK))

    n2, bib2 = document.refresh_document(doc, styles.get_style("apa"), None)
    body = doc.getText().getString()
    ok &= check("refresh visited 2 citations", n2 == 2)
    ok &= check("bibliography regenerated", bib2)
    ok &= check("APA rendered", "(Romero, 2025)" in body)
    ok &= check("two-item cluster with locator",
                "Ghali, 2008, p. 281" in body)
    ok &= check("Ghali bibliography entry",
                "Ghali, S. (2008)." in body)

    # Importing again must be a no-op: leftover controls are untagged, so
    # they must not be converted a second time into phantom citations.
    n3, _, removed3, _ = word_import.convert_document(doc)
    ok &= check("second import converts nothing", n3 == 0 and removed3 == 0)
    ok &= check("still 2 citations after second import",
                len(document.get_citation_marks(doc)) == 2)

    doc.close(False)
    print("WORD IMPORT " + ("OK" if ok else "FAILED"))
    return bool(ok)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 2002
    ctx = connect(port)
    desktop = ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.frame.Desktop", ctx)
    return 0 if run(desktop) else 1


if __name__ == "__main__":
    sys.exit(main())
