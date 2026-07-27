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


def build_cluster_items(chosen_ids, by_id, locator, prefix, suffix,
                        preset_items=None):
    """Build cluster items for the records the user picked.

    The dialog offers one locator/prefix/suffix for the whole cluster.
    When editing an existing citation whose works carry different values
    (a Word import can), returning those fields unchanged must not
    flatten them onto every work — so in that case each work that was
    already in the citation keeps its own.

    chosen_ids is in the order the works should appear; by_id maps a
    record id to its record.
    """
    preset_items = list(preset_items or [])
    original = dict((it.get("rec", {}).get("id"), it) for it in preset_items)
    untouched = False
    if preset_items:
        first = preset_items[0]
        untouched = (
            locator == (first.get("locator", "") or "").strip()
            and prefix == (first.get("prefix", "") or "").strip()
            and suffix == (first.get("suffix", "") or "").strip())
    items = []
    for rid in chosen_ids:
        rec = by_id.get(rid)
        if rec is None:
            continue
        prev = original.get(rid) if untouched else None
        if prev is not None:
            items.append({"rec": rec,
                          "locator": prev.get("locator", "") or "",
                          "prefix": prev.get("prefix", "") or "",
                          "suffix": prev.get("suffix", "") or ""})
        else:
            items.append({"rec": rec, "locator": locator,
                          "prefix": prefix, "suffix": suffix})
    return items


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
