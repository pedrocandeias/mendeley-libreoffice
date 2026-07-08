import os
import unittest

import context  # noqa: F401
from mlo import bibtex

SAMPLE = os.path.join(os.path.dirname(__file__), "sample.bib")


class TestBibtex(unittest.TestCase):
    def setUp(self):
        self.records = bibtex.parse_bibtex_file(SAMPLE)
        self.by_id = {r["id"]: r for r in self.records}

    def test_all_entries_parsed(self):
        self.assertEqual(len(self.records), 6)

    def test_article_fields(self):
        r = self.by_id["smith2020deep"]
        self.assertEqual(r["type"], "article-journal")
        self.assertEqual(r["title"], "Deep learning for DNA sequence analysis")
        self.assertEqual(r["year"], 2020)
        self.assertEqual(r["volume"], "17")
        self.assertEqual(r["issue"], "4")
        self.assertEqual(r["pages"], "321-334")
        self.assertEqual(r["doi"], "10.1038/s41592-020-0001-x")
        self.assertEqual(r["container"], "Nature Methods")

    def test_names(self):
        r = self.by_id["smith2020deep"]
        self.assertEqual(r["authors"][0], {"family": "Smith",
                                           "given": "John R."})
        self.assertEqual(r["authors"][1], {"family": "Jones",
                                           "given": "Alice"})

    def test_latex_accents(self):
        r = self.by_id["garcia2018stats"]
        fams = [a["family"] for a in r["authors"]]
        self.assertIn("García", fams)
        self.assertIn("Müller", fams)

    def test_von_particle(self):
        r = self.by_id["garcia2018stats"]
        self.assertEqual(r["authors"][2]["family"], "van der Berg")
        self.assertEqual(r["authors"][2]["given"], "Pieter")

    def test_chapter(self):
        r = self.by_id["lee2019chapter"]
        self.assertEqual(r["type"], "chapter")
        self.assertEqual(r["container"], "Systems Biology Handbook")
        self.assertEqual(len(r["editors"]), 2)
        self.assertEqual(r["place"], "Cambridge, MA")

    def test_corporate_author(self):
        r = self.by_id["who2022report"]
        self.assertEqual(r["authors"][0]["family"],
                         "World Health Organization")
        self.assertEqual(r["type"], "webpage")
        self.assertTrue(r["url"].startswith("https://www.who.int"))

    def test_latex_to_text(self):
        self.assertEqual(bibtex.latex_to_text(r"Caf\'e {Br\"uhl} -- test"),
                         'Café Brühl – test')
        self.assertEqual(bibtex.latex_to_text(r"\emph{Deep} learning"),
                         "Deep learning")

    def test_string_and_concat(self):
        recs = bibtex.parse_bibtex(
            '@string{nm = {Nature Methods}}\n'
            '@article{x, author={Doe, Jane}, title={T}, '
            'journal = nm # { Extra}, year={2001}}')
        self.assertEqual(recs[0]["container"], "Nature Methods Extra")

    def test_mendeley_groups(self):
        recs = bibtex.parse_bibtex(
            '@article{g, author={Doe, Jane}, title={T}, year={2001}, '
            'mendeley-groups = {Thesis/Ergonomics,Reading List}}')
        self.assertEqual(recs[0]["collections"],
                         ["Thesis / Ergonomics", "Reading List"])

    def test_quoted_values(self):
        recs = bibtex.parse_bibtex(
            '@article{q, author="Doe, Jane", title="A {Quoted} title", '
            'year="1999"}')
        self.assertEqual(recs[0]["title"], "A Quoted title")
        self.assertEqual(recs[0]["year"], 1999)


if __name__ == "__main__":
    unittest.main()
