import os
import unittest

import context  # noqa: F401
from mlo import payload


CLUSTER = {"items": [{"rec": {"id": "smith2020deep", "type": "article-journal",
                              "title": "Deep learning for DNA sequence analysis",
                              "authors": [{"family": "Smith", "given": "J. R."}],
                              "year": 2020},
                      "locator": "12", "prefix": "see", "suffix": ""}]}


class TestPayload(unittest.TestCase):
    def test_encode_decode_round_trip(self):
        self.assertEqual(payload.decode(payload.encode(CLUSTER)), CLUSTER)

    def test_decode_garbage_is_none(self):
        self.assertIsNone(payload.decode("not-a-payload"))
        self.assertIsNone(payload.decode(""))

    def test_chunk_word_safe_and_reassembles(self):
        incompressible = os.urandom(1500).hex()
        encoded = payload.encode(
            {"items": [dict(CLUSTER["items"][0], suffix=incompressible)]})
        chunks = payload.chunk(encoded)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(c) <= payload.CHUNK_LEN for c in chunks))
        self.assertEqual("".join(chunks), encoded)

    def test_chunk_empty_payload(self):
        self.assertEqual(payload.chunk(""), [""])

    def test_bookmark_names_word_compatible(self):
        name = payload.bookmark_name(payload.new_key())
        self.assertLessEqual(len(name), 40)       # Word's bookmark limit
        self.assertNotIn(" ", name)
        self.assertLessEqual(len(payload.BIB_BOOKMARK), 40)

    def test_key_from_bookmark(self):
        key = payload.new_key()
        self.assertEqual(payload.key_from_bookmark("MLO_C_" + key), key)
        self.assertIsNone(payload.key_from_bookmark("MLO_C_" + key + "_1"))
        self.assertIsNone(payload.key_from_bookmark("MLO_C_XYZ"))
        self.assertIsNone(payload.key_from_bookmark("SomeBookmark"))

    def test_key_from_prop(self):
        key = payload.new_key()
        self.assertEqual(payload.key_from_prop("MLO_DATA_%s_0" % key), key)
        self.assertEqual(payload.key_from_prop("MLO_DATA_%s_12" % key), key)
        self.assertIsNone(payload.key_from_prop("MLO_DATA_%s" % key))
        self.assertIsNone(payload.key_from_prop("OtherProp"))

    def test_legacy_mark_round_trip(self):
        name = (payload.LEGACY_MARK_PREFIX + payload.new_key() + " "
                + payload.encode(CLUSTER))
        self.assertEqual(payload.decode_legacy_mark(name), CLUSTER)
        self.assertIsNone(payload.decode_legacy_mark("MLO_CITE 1 truncated"))
        self.assertIsNone(payload.decode_legacy_mark("unrelated"))


if __name__ == "__main__":
    unittest.main()
