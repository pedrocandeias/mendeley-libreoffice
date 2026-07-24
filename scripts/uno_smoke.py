#!/usr/bin/env python3
"""Headless smoke test for the UNO document layer.

Run with LibreOffice's bundled python while a headless soffice is
listening:  soffice --headless --accept="socket,host=localhost,port=2002;urp;"
"""

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

    from mlo import bibtex, document, styles

    records = bibtex.parse_bibtex_file(ROOT + "/tests/sample.bib")
    by_id = {r["id"]: r for r in records}
    text = doc.getText()
    vc = doc.getCurrentController().getViewCursor()

    ok = True

    # --- insert two citation clusters and a bibliography
    text.insertString(text.getEnd(), "Deep learning matters ", False)
    vc.gotoRange(text.getEnd(), False)
    document.insert_citation_mark(
        doc, {"items": [{"rec": by_id["smith2020deep"]}]}, "(pending)")

    text.insertString(text.getEnd(), " and so does statistics ", False)
    vc.gotoRange(text.getEnd(), False)
    document.insert_citation_mark(
        doc, {"items": [{"rec": by_id["garcia2018stats"], "locator": "12"},
                        {"rec": by_id["lee2019chapter"]}]}, "(pending)")

    text.insertString(text.getEnd(), ".", False)
    vc.gotoRange(text.getEnd(), False)
    document.insert_bibliography_section(doc)

    ok &= check("two marks found",
                len(document.get_citation_marks(doc)) == 2)
    ok &= check("bibliography section exists", document.has_bibliography(doc))

    # --- refresh in IEEE (numeric)
    n, bib = document.refresh_document(doc, styles.get_style("ieee"), records)
    body = doc_text(doc)
    ok &= check("refresh visited 2 marks", n == 2)
    ok &= check("bibliography updated", bib)
    ok &= check("numeric citation [1] in text", "[1]" in body)
    ok &= check("cluster with locator rendered",
                "[2, p. 12]" in body and "[3]" in body)
    ok &= check("IEEE entry [1] present",
                '[1] J. R. Smith and A. Jones, "Deep learning' in body)
    ok &= check("IEEE entry [3] present", body.count("[3]") >= 2)

    # --- switch style and refresh again (restyle everything)
    n, bib = document.refresh_document(doc, styles.get_style("apa"), records)
    body = doc_text(doc)
    ok &= check("APA citation rendered", "(Smith & Jones, 2020)" in body)
    ok &= check("APA locator rendered",
                "(García et al., 2018, p. 12; Lee, 2019)" in body)
    ok &= check("APA entry present",
                "Smith, J. R., & Jones, A. (2020)." in body)
    ok &= check("no stale IEEE numbers", "[1]" not in body)
    ok &= check("marks survive restyle",
                len(document.get_citation_marks(doc)) == 2)

    # --- marks keep payloads decodable
    marks = document.get_citation_marks(doc)
    ok &= check("payload round-trips",
                marks[1][1]["items"][0]["rec"]["id"] == "garcia2018stats")

    doc.close(False)
    print("SMOKE " + ("OK" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
