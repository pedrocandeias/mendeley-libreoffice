#!/usr/bin/env python3
"""Smoke test do importador Mendeley Cite (Word) → formato do plugin.

Fabrica num documento Writer content controls idênticos aos que o
add-in do Word escreve (Tag MENDELEY_CITATION_v3_<base64> e
MENDELEY_BIBLIOGRAPHY), corre a conversão e verifica bookmarks,
payloads e o refresh.

Correr como uno_smoke.py: soffice headless à escuta no porto 2002.
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


def insert_control(doc, text, cursor, rendered, tag):
    cursor.setString(rendered)
    cc = doc.createInstance("com.sun.star.text.ContentControl")
    cc.Tag = tag
    text.insertTextContent(cursor, cc, True)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 2002
    ctx = connect(port)
    desktop = ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.frame.Desktop", ctx)
    doc = desktop.loadComponentFromURL("private:factory/swriter",
                                       "_blank", 0, ())

    from mlo import document, payload, styles, word_import

    text = doc.getText()
    ok = True

    # citação 1 (um item) e citação 2 (dois itens, com locator)
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

    # bibliografia Word
    text.insertControlCharacter(
        text.getEnd(), uno.getConstantByName(
            "com.sun.star.text.ControlCharacter.PARAGRAPH_BREAK"), False)
    cur = text.createTextCursorByRange(text.getEnd())
    insert_control(doc, text, cur, "Old Word bibliography",
                   "MENDELEY_BIBLIOGRAPHY")

    ok &= check("2 content controls de citação criados",
                doc.getContentControls().getCount() == 3)

    n, bib = word_import.convert_document(doc)
    ok &= check("2 clusters importados", n == 2)
    ok &= check("bibliografia convertida", bib)
    ok &= check("content controls dissolvidos",
                doc.getContentControls().getCount() == 0)

    marks = document.get_citation_marks(doc)
    ok &= check("2 bookmarks de citação", len(marks) == 2)
    ok &= check("payload com locator preservado",
                any(it.get("locator") == "281"
                    for _, c in marks for it in c["items"]))
    ok &= check("bookmark de bibliografia",
                doc.getBookmarks().hasByName(payload.BIB_BOOKMARK))

    n2, bib2 = document.refresh_document(doc, styles.get_style("apa"), None)
    body = doc.getText().getString()
    ok &= check("refresh percorreu 2 citações", n2 == 2)
    ok &= check("bibliografia regenerada", bib2)
    ok &= check("APA renderizado", "(Romero, 2025)" in body)
    ok &= check("cluster duplo com locator",
                "Ghali, 2008, p. 281" in body)
    ok &= check("entrada bibliográfica de Ghali",
                "Ghali, S. (2008)." in body)

    doc.close(False)
    print("WORD IMPORT " + ("OK" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
