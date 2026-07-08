import os
import unittest

import context  # noqa: F401
from mlo import bibtex, engine, styles

SAMPLE = os.path.join(os.path.dirname(__file__), "sample.bib")


def load():
    records = bibtex.parse_bibtex_file(SAMPLE)
    return {r["id"]: r for r in records}


def cluster(by_id, *ids, **kw):
    return {"items": [dict({"rec": by_id[i]}, **kw) for i in ids]}


class TestAuthorDate(unittest.TestCase):
    def setUp(self):
        self.by_id = load()

    def test_apa_citation_two_authors(self):
        rendered, _ = engine.process(
            [cluster(self.by_id, "smith2020deep")], styles.get_style("apa"))
        # smith2020deep and smith2020other share authors+year -> a/b
        self.assertIn("Smith & Jones", rendered[0])
        self.assertIn("2020", rendered[0])

    def test_apa_et_al(self):
        rendered, _ = engine.process(
            [cluster(self.by_id, "garcia2018stats")],
            styles.get_style("apa"))
        self.assertEqual(rendered[0], "(García et al., 2018)")

    def test_apa_disambiguation(self):
        clusters = [cluster(self.by_id, "smith2020other"),
                    cluster(self.by_id, "smith2020deep")]
        rendered, entries = engine.process(clusters, styles.get_style("apa"))
        # "Another view..." sorts before "Deep learning..." -> a / b
        self.assertEqual(rendered[0], "(Smith & Jones, 2020a)")
        self.assertEqual(rendered[1], "(Smith & Jones, 2020b)")
        self.assertTrue(any("(2020a)" in e for e in entries))
        self.assertTrue(any("(2020b)" in e for e in entries))

    def test_apa_locator(self):
        rendered, _ = engine.process(
            [cluster(self.by_id, "garcia2018stats", locator="12-14")],
            styles.get_style("apa"))
        self.assertEqual(rendered[0], "(García et al., 2018, pp. 12–14)")

    def test_apa_multi_item_cluster(self):
        rendered, _ = engine.process(
            [cluster(self.by_id, "garcia2018stats", "lee2019chapter")],
            styles.get_style("apa"))
        self.assertEqual(rendered[0], "(García et al., 2018; Lee, 2019)")

    def test_apa_entry_article(self):
        _, entries = engine.process(
            [cluster(self.by_id, "smith2020deep")], styles.get_style("apa"))
        e = entries[0]
        self.assertTrue(e.startswith("Smith, J. R., & Jones, A. (2020)."))
        self.assertIn("Nature Methods, 17(4), 321–334.", e)
        self.assertIn("https://doi.org/10.1038/s41592-020-0001-x", e)

    def test_apa_bibliography_sorted(self):
        clusters = [cluster(self.by_id, "nguyen2021attention"),
                    cluster(self.by_id, "garcia2018stats")]
        _, entries = engine.process(clusters, styles.get_style("apa"))
        self.assertTrue(entries[0].startswith("García"))
        self.assertTrue(entries[1].startswith("Nguyen"))

    def test_harvard_citation(self):
        rendered, _ = engine.process(
            [cluster(self.by_id, "smith2020deep", locator="5")],
            styles.get_style("harvard"))
        self.assertEqual(rendered[0], "(Smith and Jones, 2020, p. 5)")

    def test_harvard_entry_book(self):
        _, entries = engine.process(
            [cluster(self.by_id, "garcia2018stats")],
            styles.get_style("harvard"))
        e = entries[0]
        self.assertIn("(2018)", e)
        self.assertIn("Statistical Methods in Biology.", e)
        self.assertIn("3rd edn.", e)
        self.assertIn("Berlin: Springer.", e)

    def test_chicago_citation(self):
        rendered, _ = engine.process(
            [cluster(self.by_id, "smith2020deep", locator="45")],
            styles.get_style("chicago-ad"))
        self.assertEqual(rendered[0], "(Smith and Jones 2020, 45)")

    def test_corporate_author_citation(self):
        rendered, _ = engine.process(
            [cluster(self.by_id, "who2022report")], styles.get_style("apa"))
        self.assertEqual(rendered[0], "(World Health Organization, 2022)")


class TestNumeric(unittest.TestCase):
    def setUp(self):
        self.by_id = load()

    def test_ieee_numbering_by_first_appearance(self):
        clusters = [cluster(self.by_id, "lee2019chapter"),
                    cluster(self.by_id, "smith2020deep"),
                    cluster(self.by_id, "lee2019chapter")]
        rendered, entries = engine.process(clusters, styles.get_style("ieee"))
        self.assertEqual(rendered[0], "[1]")
        self.assertEqual(rendered[1], "[2]")
        self.assertEqual(rendered[2], "[1]")
        self.assertTrue(entries[0].startswith("[1] K.-Y. Lee,"))
        self.assertTrue(entries[1].startswith("[2] J. R. Smith and A. Jones,"))

    def test_ieee_range_collapse(self):
        clusters = [cluster(self.by_id, "smith2020deep"),
                    cluster(self.by_id, "smith2020other"),
                    cluster(self.by_id, "garcia2018stats"),
                    cluster(self.by_id, "who2022report"),
                    cluster(self.by_id, "smith2020deep", "smith2020other",
                            "garcia2018stats", "who2022report"),
                    cluster(self.by_id, "smith2020deep", "smith2020other",
                            "who2022report")]
        rendered, _ = engine.process(clusters, styles.get_style("ieee"))
        self.assertEqual(rendered[-2], "[1]–[4]")
        self.assertEqual(rendered[-1], "[1], [2], [4]")

    def test_ieee_entry_article(self):
        _, entries = engine.process(
            [cluster(self.by_id, "smith2020deep")], styles.get_style("ieee"))
        e = entries[0]
        self.assertIn('"Deep learning for DNA sequence analysis,"', e)
        self.assertIn("vol. 17,", e)
        self.assertIn("no. 4,", e)
        self.assertIn("pp. 321–334,", e)
        self.assertIn("2020.", e)

    def test_vancouver_citation_and_entry(self):
        clusters = [cluster(self.by_id, "smith2020deep"),
                    cluster(self.by_id, "smith2020other"),
                    cluster(self.by_id, "smith2020deep", "smith2020other")]
        rendered, entries = engine.process(clusters,
                                           styles.get_style("vancouver"))
        self.assertEqual(rendered[0], "(1)")
        self.assertEqual(rendered[2], "(1,2)")
        self.assertTrue(entries[0].startswith("1. Smith JR, Jones A."))
        self.assertIn("2020;17(4):321-334.", entries[0])

    def test_numeric_locator_disables_collapse(self):
        clusters = [cluster(self.by_id, "smith2020deep", locator="7")]
        rendered, _ = engine.process(clusters, styles.get_style("ieee"))
        self.assertEqual(rendered[0], "[1, p. 7]")


class TestEngine(unittest.TestCase):
    def test_snapshot_only_processing(self):
        rec = {"id": "x1", "type": "article-journal", "title": "T",
               "authors": [{"family": "Doe", "given": "Jane"}],
               "year": 2005, "container": "J", "volume": "1", "issue": "",
               "pages": "1-2", "publisher": "", "place": "", "doi": "",
               "url": "", "edition": ""}
        rendered, entries = engine.process(
            [{"items": [{"rec": rec}]}], styles.get_style("apa"))
        self.assertEqual(rendered[0], "(Doe, 2005)")
        self.assertEqual(len(entries), 1)

    def test_no_year(self):
        rec = {"id": "x2", "type": "generic", "title": "Untitled thing",
               "authors": [{"family": "Doe", "given": "J"}], "year": None,
               "container": "", "volume": "", "issue": "", "pages": "",
               "publisher": "", "place": "", "doi": "", "url": "",
               "edition": ""}
        rendered, _ = engine.process(
            [{"items": [{"rec": rec}]}], styles.get_style("apa"))
        self.assertEqual(rendered[0], "(Doe, n.d.)")


if __name__ == "__main__":
    unittest.main()
