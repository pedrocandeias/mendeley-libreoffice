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


class TestLeftoverEntries(unittest.TestCase):
    """Recognising old Word bibliography entries left in the text."""

    def setUp(self):
        cluster = word_import.citation_to_cluster(CITATION)
        self.prints = word_import.entry_fingerprints([cluster])

    def test_entry_by_title(self):
        self.assertTrue(word_import.looks_like_entry(
            "Smith, J. R., & Jones, A. (2020). Deep learning for DNA "
            "sequence analysis. Nature Methods, 17(4), 321-334.",
            self.prints))

    def test_entry_by_doi(self):
        self.assertTrue(word_import.looks_like_entry(
            "Smith, J. (2020). A shortened title. "
            "https://doi.org/10.1038/s41592-020-0001-x", self.prints))

    def test_typographic_punctuation_and_wrapping(self):
        # Word renders quotes and dashes prettily and may wrap entries.
        self.assertTrue(word_import.looks_like_entry(
            "Deep learning\n  for DNA sequence analysis", self.prints))

    def test_ordinary_text_is_not_an_entry(self):
        self.assertFalse(word_import.looks_like_entry(
            "The next chapter discusses sequencing in general.",
            self.prints))
        self.assertFalse(word_import.looks_like_entry("", self.prints))

    def test_short_titles_are_not_fingerprints(self):
        cluster = word_import.citation_to_cluster(
            {"citationItems": [{"itemData": {"id": "x", "title": "Hands"}}]})
        self.assertEqual(word_import.entry_fingerprints([cluster]), set())

    def test_no_fingerprints_matches_nothing(self):
        self.assertFalse(word_import.looks_like_entry("Anything", set()))


E, B, O = word_import.ENTRY, word_import.BLANK, word_import.OTHER


class TestSweepPlan(unittest.TestCase):
    """Deciding how far the stranded old reference list reaches."""

    def test_entries_and_separators_go(self):
        delete, left = word_import.sweep_plan([E, B, E, B, E])
        self.assertEqual(delete, [0, 1, 2, 3, 4])
        self.assertEqual(left, 0)

    def test_stops_at_the_last_entry(self):
        delete, left = word_import.sweep_plan([E, E, O, O, O])
        self.assertEqual(delete, [0, 1])
        self.assertEqual(left, 0)

    def test_steps_over_unrecognised_entries(self):
        delete, left = word_import.sweep_plan([E, O, O, E])
        self.assertEqual(delete, [0, 3])       # the two misses stay
        self.assertEqual(left, 2)

    def test_gap_larger_than_tolerated_ends_the_list(self):
        kinds = [E] + [O] * (word_import.SWEEP_GAP + 1) + [E]
        delete, left = word_import.sweep_plan(kinds)
        self.assertEqual(delete, [0])
        self.assertEqual(left, 0)

    def test_blanks_do_not_count_towards_the_gap(self):
        delete, _ = word_import.sweep_plan([E] + [B] * 20 + [E])
        self.assertEqual(delete, list(range(22)))

    def test_no_entries_at_all(self):
        self.assertEqual(word_import.sweep_plan([O, B, O]), ([], 0))
        self.assertEqual(word_import.sweep_plan([]), ([], 0))


if __name__ == "__main__":
    unittest.main()
