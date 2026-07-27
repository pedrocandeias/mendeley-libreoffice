import base64
import json
import unittest

import context  # noqa: F401
from mlo import word_import


def make_tag(data: dict) -> str:
    raw = json.dumps(data).encode("utf-8")
    return word_import.TAG_PREFIX + base64.b64encode(raw).decode("ascii")


ITEM = {
    "id": "abc-123",
    "type": "article-journal",
    "title": "Deep learning for DNA sequence analysis",
    "author": [{"family": "Smith", "given": "Jane R."},
               {"family": "Jones", "given": "Alan"}],
    "issued": {"date-parts": [[2020, 5, 1]]},
    "container-title": "Nature Methods",
    "volume": 17, "issue": "4", "page": "321-334",
    "DOI": "10.1038/s41592-020-0001-x",
}

CITATION = {
    "citationID": "MENDELEY_CITATION_x",
    "citationItems": [
        {"id": "abc-123", "itemData": ITEM, "locator": "12"},
    ],
}


class TestDecodeTag(unittest.TestCase):
    def test_round_trip(self):
        data = word_import.decode_tag(make_tag(CITATION))
        self.assertEqual(data["citationID"], "MENDELEY_CITATION_x")

    def test_unpadded_base64(self):
        tag = make_tag(CITATION).rstrip("=")
        self.assertIsNotNone(word_import.decode_tag(tag))

    def test_foreign_tags(self):
        self.assertIsNone(word_import.decode_tag("SomethingElse"))
        self.assertIsNone(word_import.decode_tag(""))
        self.assertIsNone(word_import.decode_tag(None))
        self.assertIsNone(word_import.decode_tag(
            word_import.TAG_PREFIX + "not-base64!!"))


class TestCslToRecord(unittest.TestCase):
    def test_fields(self):
        r = word_import.csl_to_record(ITEM)
        self.assertEqual(r["id"], "abc-123")
        self.assertEqual(r["type"], "article-journal")
        self.assertEqual(r["year"], 2020)
        self.assertEqual(r["authors"][0], {"family": "Smith",
                                           "given": "Jane R."})
        self.assertEqual(r["container"], "Nature Methods")
        self.assertEqual(r["volume"], "17")
        self.assertEqual(r["pages"], "321-334")
        self.assertEqual(r["doi"], "10.1038/s41592-020-0001-x")

    def test_type_aliases_and_fallback(self):
        self.assertEqual(word_import.csl_to_record(
            {"type": "book-section"})["type"], "chapter")
        self.assertEqual(word_import.csl_to_record(
            {"type": "dataset"})["type"], "generic")
        self.assertEqual(word_import.csl_to_record({})["type"], "generic")

    def test_missing_year(self):
        self.assertIsNone(word_import.csl_to_record(
            {"issued": {"date-parts": [[]]}})["year"])
        self.assertIsNone(word_import.csl_to_record({})["year"])


class TestCitationToCluster(unittest.TestCase):
    def test_cluster(self):
        c = word_import.citation_to_cluster(CITATION)
        self.assertEqual(len(c["items"]), 1)
        self.assertEqual(c["items"][0]["locator"], "12")
        self.assertEqual(c["items"][0]["rec"]["title"], ITEM["title"])

    def test_empty(self):
        self.assertIsNone(word_import.citation_to_cluster({}))
        self.assertIsNone(word_import.citation_to_cluster(
            {"citationItems": [{"itemData": {}}]}))


if __name__ == "__main__":
    unittest.main()
