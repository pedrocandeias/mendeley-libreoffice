"""Importa citações do Mendeley Cite (Word) para o formato do plugin.

Os documentos geridos pelo add-in Mendeley Cite do Microsoft Word
guardam cada citação num content control cujo Tag transporta o estado
completo em base64:

    MENDELEY_CITATION_v3_<base64(json)>

O JSON contém os citationItems com o registo CSL integral de cada obra
citada (itemData), além de locator/prefix/suffix. A bibliografia vive
num content control com Tag MENDELEY_BIBLIOGRAPHY.

Este módulo converte esses content controls no formato nativo do
plugin — bookmarks `MLO_C_<key>` com payloads em propriedades do
documento e o bookmark `MLO_BIBLIOGRAPHY` — tornando o documento
gerível no LibreOffice. A conversão é unidireccional: o add-in do Word
deixa de reconhecer as citações convertidas.

As funções puras (descodificação e mapeamento CSL→registo) não dependem
de UNO e são testáveis fora do LibreOffice.
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


# ---------------------------------------------------------------- puras

def decode_tag(tag: str):
    """Descodifica o Tag de um content control de citação; None se alheio."""
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
    """Converte um itemData CSL-JSON no formato interno de registo."""
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
    """Converte o JSON de uma citação Word num cluster do plugin."""
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
    """Remove um content control preservando o texto; devolve um cursor
    que abrange esse texto."""
    anchor = cc.getAnchor()
    text = anchor.getText()
    cursor = text.createTextCursorByRange(anchor)
    text.removeTextContent(cc)
    if cursor.getString() != keep_text:
        cursor.setString(keep_text)
    return text, cursor


def convert_document(doc):
    """Converte todas as citações Mendeley Cite (Word) do documento.

    Devolve (nº de clusters convertidos, bibliografia convertida?).
    """
    from . import document

    try:
        controls_access = doc.getContentControls()
    except Exception:
        raise RuntimeError(
            "Esta versão do LibreOffice não expõe content controls "
            "(é necessário LibreOffice 7.4 ou mais recente).")

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
