"""Citation payload encoding and naming (pure Python, no UNO).

A citation cluster is serialised as base64url(zlib(json)). Since 0.2.0
the payload lives in user-defined document properties — chunked so each
value stays within Microsoft Word's 255-character limit for string
properties — while a short bookmark marks the citation in the text:

    bookmark   MLO_C_<8-hex-key>            (spans the rendered text)
    properties MLO_DATA_<key>_0, _1, ...    (payload chunks)

Bookmarks and custom document properties survive DOCX round-trips in
both LibreOffice and Word, unlike the pre-0.2 reference-mark names,
which only survived in ODF documents.
"""

import base64
import json
import uuid
import zlib

CITE_BOOKMARK_PREFIX = "MLO_C_"
DATA_PROP_PREFIX = "MLO_DATA_"
BIB_BOOKMARK = "MLO_BIBLIOGRAPHY"
CHUNK_LEN = 255                      # Word-safe property value length
LEGACY_MARK_PREFIX = "MLO_CITE 1 "   # pre-0.2 reference-mark format


def new_key():
    return uuid.uuid4().hex[:8]


def encode(cluster):
    raw = json.dumps(cluster, ensure_ascii=False,
                     separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(zlib.compress(raw, 9)).decode("ascii")


def decode(payload):
    try:
        raw = zlib.decompress(base64.urlsafe_b64decode(payload.encode("ascii")))
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


def chunk(payload):
    return [payload[i:i + CHUNK_LEN]
            for i in range(0, len(payload), CHUNK_LEN)] or [""]


def bookmark_name(key):
    return CITE_BOOKMARK_PREFIX + key


def prop_name(key, n):
    return "%s%s_%d" % (DATA_PROP_PREFIX, key, n)


def key_from_bookmark(name):
    """Extract the citation key from a bookmark name, or None.

    Strict on shape (exactly 8 hex chars) so that renamed duplicates
    created by copy/paste ("MLO_C_abc12345_1") are left alone.
    """
    if not name.startswith(CITE_BOOKMARK_PREFIX):
        return None
    key = name[len(CITE_BOOKMARK_PREFIX):]
    if len(key) == 8 and all(c in "0123456789abcdef" for c in key):
        return key
    return None


def key_from_prop(name):
    """Extract the citation key from a property name, or None."""
    if not name.startswith(DATA_PROP_PREFIX):
        return None
    rest = name[len(DATA_PROP_PREFIX):]
    key, _, n = rest.rpartition("_")
    if len(key) == 8 and n.isdigit():
        return key
    return None


def decode_legacy_mark(name):
    """Decode a pre-0.2 reference-mark name into a cluster, or None."""
    if not name.startswith(LEGACY_MARK_PREFIX):
        return None
    try:
        payload = name[len(LEGACY_MARK_PREFIX):].split(" ", 1)[1]
    except IndexError:
        return None
    return decode(payload)
