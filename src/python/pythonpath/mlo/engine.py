"""Citation processing engine.

Takes citation clusters in document order plus a style, and produces:
  * the rendered text for each cluster
  * the ordered list of bibliography entries

A cluster is {"items": [{"rec": record, "locator": str,
                         "prefix": str, "suffix": str}]}.
Records embedded in clusters are snapshots stored in the document, so
processing works even when the library is unavailable; callers should
substitute fresher library records into the clusters before processing.
"""


def process(clusters, style):
    """Return (rendered_citations, bibliography_entries)."""
    works = {}     # id -> record (first-seen snapshot)
    order = []     # ids in order of first appearance
    for cluster in clusters:
        for it in cluster["items"]:
            rid = it["rec"].get("id")
            if rid not in works:
                works[rid] = it["rec"]
                order.append(rid)

    numbers = {}
    year_suffix = {}
    if style.kind == "numeric":
        bib_ids = order
        numbers = dict((rid, i + 1) for i, rid in enumerate(order))
    else:
        bib_ids = sorted(works, key=lambda rid: style.sort_key(works[rid]))
        # Disambiguate same author(s) + same year with a/b/c suffixes.
        groups = {}
        for rid in bib_ids:
            rec = works[rid]
            key = (style.short_names(rec), rec.get("year"))
            groups.setdefault(key, []).append(rid)
        for (names, year), rids in groups.items():
            if len(rids) > 1 and year:
                for i, rid in enumerate(rids):
                    year_suffix[rid] = chr(ord("a") + i)

    rendered = []
    for cluster in clusters:
        items = []
        for it in cluster["items"]:
            rid = it["rec"].get("id")
            items.append({
                "rec": works[rid],
                "locator": it.get("locator", ""),
                "prefix": it.get("prefix", ""),
                "suffix": it.get("suffix", ""),
                "year_suffix": year_suffix.get(rid, ""),
                "number": numbers.get(rid),
            })
        rendered.append(style.citation(items))

    entries = [style.entry(works[rid],
                           year_suffix=year_suffix.get(rid, ""),
                           number=numbers.get(rid))
               for rid in bib_ids]
    return rendered, entries
