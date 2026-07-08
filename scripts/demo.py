#!/usr/bin/env python3
"""Render tests/sample.bib in every built-in style (visual check)."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "src", "python", "pythonpath"))

from mlo import bibtex, engine, styles  # noqa: E402

records = bibtex.parse_bibtex_file(
    os.path.join(os.path.dirname(__file__), "..", "tests", "sample.bib"))
by_id = {r["id"]: r for r in records}

clusters = [
    {"items": [{"rec": by_id["smith2020deep"]}]},
    {"items": [{"rec": by_id["garcia2018stats"], "locator": "12-14"}]},
    {"items": [{"rec": by_id["lee2019chapter"]},
               {"rec": by_id["nguyen2021attention"]}]},
    {"items": [{"rec": by_id["smith2020other"]}]},
    {"items": [{"rec": by_id["who2022report"], "prefix": "see"}]},
]

for style in styles.STYLES:
    print("=" * 72)
    print(style.name)
    print("=" * 72)
    rendered, entries = engine.process(clusters, style)
    print("In text:  " + "  |  ".join(rendered))
    print()
    for e in entries:
        print("  " + e)
    print()
