#!/usr/bin/env python3
"""DOCX round-trip test for the bookmark storage backend.

Builds a document with live citations, saves it as .docx, reloads it and
checks that citations and bibliography are still live and restylable.
Also checks that a pre-0.2 reference-mark citation is migrated to the
bookmark format on refresh.

Run like uno_smoke.py: a headless soffice must be listening, e.g.
  soffice --headless --accept="socket,host=localhost,port=2002;urp;"
"""

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT + "/src/python/pythonpath")

import uno  # noqa: E402
import unohelper  # noqa: E402
from com.sun.star.beans import PropertyValue  # noqa: E402


def connect(port, attempts=30):
    local = uno.getComponentContext()
    resolver = local.ServiceManager.createInstanceWithContext(
        "com.sun.star.bridge.UnoUrlResolver", local)
    url = ("uno:socket,host=localhost,port=%d;urp;"
           "StarOffice.ComponentContext" % port)
    for i in range(attempts):
        try:
            return resolver.resolve(url)
        except Exception:
            time.sleep(1)
    raise SystemExit("could not connect to soffice on port %d" % port)


def doc_text(doc):
    out = []
    enum = doc.getText().createEnumeration()
    while enum.hasMoreElements():
        para = enum.nextElement()
        try:
            out.append(para.getString())
        except Exception:
            out.append("")
    return "\n".join(out)


def check(label, cond):
    print(("PASS  " if cond else "FAIL  ") + label)
    return bool(cond)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 2002
    ctx = connect(port)
    smgr = ctx.ServiceManager
    desktop = smgr.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
    doc = desktop.loadComponentFromURL("private:factory/swriter",
                                       "_blank", 0, ())

    from mlo import bibtex, document, payload, styles

    records = bibtex.parse_bibtex_file(ROOT + "/tests/sample.bib")
    by_id = {r["id"]: r for r in records}
    text = doc.getText()
    vc = doc.getCurrentController().getViewCursor()

    ok = True

    # --- build a document: two bookmark citations + one legacy mark
    text.insertString(text.getEnd(), "Deep learning matters ", False)
    vc.gotoRange(text.getEnd(), False)
    document.insert_citation_mark(
        doc, {"items": [{"rec": by_id["smith2020deep"]}]}, "(pending)")

    text.insertString(text.getEnd(), " and so does statistics ", False)
    vc.gotoRange(text.getEnd(), False)
    document.insert_citation_mark(
        doc, {"items": [{"rec": by_id["garcia2018stats"], "locator": "12"}]},
        "(pending)")

    # A pre-0.2 citation: reference mark carrying the payload in its name.
    text.insertString(text.getEnd(), " and legacy history ", False)
    cursor = text.createTextCursorByRange(text.getEnd())
    cursor.setString("(legacy)")
    legacy = doc.createInstance("com.sun.star.text.ReferenceMark")
    legacy.setName(document.encode_cluster(
        {"items": [{"rec": by_id["lee2019chapter"]}]}))
    text.insertTextContent(cursor, legacy, True)

    text.insertString(text.getEnd(), ".", False)
    vc.gotoRange(text.getEnd(), False)
    document.insert_bibliography_section(doc)

    n, bib = document.refresh_document(doc, styles.get_style("apa"), records)
    ok &= check("refresh visited 3 citations", n == 3)
    ok &= check("legacy mark migrated to bookmark",
                len(doc.getReferenceMarks().getElementNames()) == 0)

    # --- save as DOCX and reload
    out = os.path.join(ROOT, "dist", "docx-roundtrip-test.docx")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    url = unohelper.systemPathToFileUrl(out)
    doc.storeToURL(url, (PropertyValue(Name="FilterName",
                                       Value="MS Word 2007 XML"),))
    doc.close(False)

    doc = desktop.loadComponentFromURL(url, "_blank", 0, ())
    marks = document.get_citation_marks(doc)
    ok &= check("3 citations survive DOCX reload", len(marks) == 3)
    ok &= check("payloads decode after reload",
                sorted(m[1]["items"][0]["rec"]["id"] for m in marks)
                == ["garcia2018stats", "lee2019chapter", "smith2020deep"])
    ok &= check("bibliography bookmark survives",
                doc.getBookmarks().hasByName(payload.BIB_BOOKMARK))

    # --- restyle the reloaded DOCX
    n, bib = document.refresh_document(doc, styles.get_style("ieee"), records)
    body = doc_text(doc)
    ok &= check("refresh after reload visited 3 citations", n == 3)
    ok &= check("bibliography updated after reload", bib)
    ok &= check("numeric citation [1] rendered", "[1]" in body)
    ok &= check("locator rendered", "[2, p. 12]" in body)
    ok &= check("no stale APA citations", "(Smith & Jones, 2020)" not in body)

    doc.close(False)
    try:
        os.remove(out)
    except OSError:
        pass
    print("DOCX ROUNDTRIP " + ("OK" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
