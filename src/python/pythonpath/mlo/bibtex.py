"""Minimal, dependency-free BibTeX parser.

Parses .bib files exported from Mendeley Reference Manager (File >
Export All > BibTeX) into the internal record format used by the
citation engine:

    {
        "id": str,            # cite key
        "type": str,          # article-journal | book | chapter |
                              # paper-conference | thesis | report |
                              # webpage | generic
        "title": str,
        "authors": [{"family": str, "given": str}],
        "editors": [{"family": str, "given": str}],
        "year": int | None,
        "container": str,     # journal / book / proceedings title
        "volume": str, "issue": str, "pages": str,
        "publisher": str, "place": str,
        "doi": str, "url": str, "edition": str,
    }
"""

import re
import unicodedata

ENTRY_TYPE_MAP = {
    "article": "article-journal",
    "book": "book",
    "inbook": "chapter",
    "incollection": "chapter",
    "inproceedings": "paper-conference",
    "conference": "paper-conference",
    "proceedings": "book",
    "phdthesis": "thesis",
    "mastersthesis": "thesis",
    "thesis": "thesis",
    "techreport": "report",
    "report": "report",
    "online": "webpage",
    "electronic": "webpage",
    "webpage": "webpage",
    "misc": "generic",
    "unpublished": "generic",
    "booklet": "generic",
    "manual": "report",
}

_COMBINING = {
    "'": "́", "`": "̀", '"': "̈", "^": "̂",
    "~": "̃", "=": "̄", ".": "̇", "u": "̆",
    "v": "̌", "H": "̋", "c": "̧", "k": "̨",
    "r": "̊", "b": "̱", "d": "̣", "t": "͡",
}

_SYMBOLS = {
    r"\ss": "ß", r"\o": "ø", r"\O": "Ø", r"\ae": "æ", r"\AE": "Æ",
    r"\aa": "å", r"\AA": "Å", r"\l": "ł", r"\L": "Ł", r"\i": "ı",
    r"\j": "ȷ", r"\oe": "œ", r"\OE": "Œ", r"\&": "&", r"\%": "%",
    r"\$": "$", r"\_": "_", r"\#": "#", r"\{": "{", r"\}": "}",
    r"\textendash": "–", r"\textemdash": "—",
}


def latex_to_text(s):
    """Convert common LaTeX markup/escapes to plain unicode text."""
    if not s:
        return ""
    # Accent commands: \'e  \'{e}  \c{c}  \v{s}  \'\i ...
    def _accent(m):
        letter = m.group(2) or m.group(3)
        if letter in ("\\i", "\\j"):        # dotless i/j take the dot back
            letter = letter[1]
        return unicodedata.normalize("NFC", letter + _COMBINING[m.group(1)])

    s = re.sub(r"\\(['`\"^~=.uvHckrbdt])\s*(?:\{(\\?[A-Za-z])\}|(\\?[A-Za-z]))",
               _accent, s)
    for k, v in _SYMBOLS.items():
        s = s.replace(k + "{}", v).replace(k, v)
    # Formatting commands: keep the argument, drop the command.
    for _ in range(4):
        s = re.sub(
            r"\\(?:emph|textit|textbf|textsc|texttt|textsl|textup|"
            r"mkbibquote|mkbibemph|url|href|uppercase|lowercase|mbox)"
            r"\{([^{}]*)\}",
            r"\1", s)
    s = re.sub(r"\\[A-Za-z]+\s*", "", s)   # any leftover commands
    s = s.replace("---", "—").replace("--", "–")
    s = s.replace("~", " ")
    s = s.replace("{", "").replace("}", "")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def parse_names(s):
    """Parse a BibTeX author/editor field into name dicts."""
    names = []
    for part in re.split(r"\s+and\s+", s.strip()):
        part = part.strip()
        if not part or part.lower() == "others":
            continue
        # {Corporate Name} is a single protected literal name.
        if part.startswith("{") and part.endswith("}"):
            names.append({"family": latex_to_text(part), "given": ""})
            continue
        part = latex_to_text(part)
        if "," in part:
            pieces = [p.strip() for p in part.split(",")]
            if len(pieces) >= 3:      # von Last, Jr, First
                family = pieces[0] + " " + pieces[1]
                given = pieces[2]
            else:                     # Last, First
                family, given = pieces[0], pieces[1]
        else:
            tokens = part.split()
            if len(tokens) == 1:
                family, given = tokens[0], ""
            else:
                # attach lowercase "von" particles to the family name
                idx = len(tokens) - 1
                for i, tok in enumerate(tokens[:-1]):
                    if tok[:1].islower():
                        idx = i
                        break
                family = " ".join(tokens[idx:])
                given = " ".join(tokens[:idx])
        names.append({"family": family.strip(), "given": given.strip()})
    return names


class _Scanner:
    def __init__(self, text):
        self.text = text
        self.pos = 0

    def skip_ws(self):
        while self.pos < len(self.text) and self.text[self.pos].isspace():
            self.pos += 1

    def read_balanced(self, open_ch, close_ch):
        """Read a balanced {...} or (...) group. pos is at open_ch."""
        depth = 0
        start = self.pos
        while self.pos < len(self.text):
            c = self.text[self.pos]
            if c == open_ch:
                depth += 1
            elif c == close_ch:
                depth -= 1
                if depth == 0:
                    self.pos += 1
                    return self.text[start + 1:self.pos - 1]
            self.pos += 1
        raise ValueError("Unbalanced %s at %d" % (open_ch, start))


def _parse_value(sc, strings):
    """Parse a field value (handles {..}, ".." , numbers and # concat)."""
    out = []
    while True:
        sc.skip_ws()
        if sc.pos >= len(sc.text):
            break
        c = sc.text[sc.pos]
        if c == "{":
            out.append(sc.read_balanced("{", "}"))
        elif c == '"':
            sc.pos += 1
            start = sc.pos
            depth = 0
            while sc.pos < len(sc.text):
                ch = sc.text[sc.pos]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                elif ch == '"' and depth == 0:
                    break
                sc.pos += 1
            out.append(sc.text[start:sc.pos])
            sc.pos += 1
        else:
            m = re.match(r"[A-Za-z0-9_.:+/-]+", sc.text[sc.pos:])
            if not m:
                break
            word = m.group(0)
            sc.pos += len(word)
            out.append(strings.get(word.lower(), word))
        sc.skip_ws()
        if sc.pos < len(sc.text) and sc.text[sc.pos] == "#":
            sc.pos += 1
            continue
        break
    return "".join(out)


def _parse_fields(body, strings):
    sc = _Scanner(body)
    sc.skip_ws()
    m = re.match(r"[^,\s{}]+", body[sc.pos:])
    key = m.group(0) if m else ""
    sc.pos += len(key)
    fields = {}
    while True:
        sc.skip_ws()
        if sc.pos >= len(sc.text):
            break
        if sc.text[sc.pos] == ",":
            sc.pos += 1
            sc.skip_ws()
        if sc.pos >= len(sc.text):
            break
        m = re.match(r"[A-Za-z][A-Za-z0-9_-]*", sc.text[sc.pos:])
        if not m:
            break
        name = m.group(0).lower()
        sc.pos += len(name)
        sc.skip_ws()
        if sc.pos >= len(sc.text) or sc.text[sc.pos] != "=":
            break
        sc.pos += 1
        fields[name] = _parse_value(sc, strings)
    return key, fields


def _extract_year(fields):
    for f in ("year", "date", "issued"):
        v = fields.get(f, "")
        m = re.search(r"\b(1[5-9]\d\d|2\d\d\d)\b", v)
        if m:
            return int(m.group(1))
    return None


def _to_record(entry_type, key, fields):
    rtype = ENTRY_TYPE_MAP.get(entry_type.lower(), "generic")
    if rtype == "generic" and fields.get("url") and not fields.get("journal"):
        rtype = "webpage"
    container = (fields.get("journal") or fields.get("journaltitle")
                 or fields.get("booktitle") or fields.get("series") or "")
    publisher = (fields.get("publisher") or fields.get("institution")
                 or fields.get("school") or fields.get("organization") or "")
    pages = (fields.get("pages") or "").replace("--", "-").replace(" ", "")
    doi = (fields.get("doi") or "").strip()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)
    # Mendeley Desktop's export tags entries with their collections.
    groups = fields.get("mendeley-groups") or fields.get("groups") or ""
    collections = [latex_to_text(g.strip()).replace("/", " / ")
                   for g in groups.split(",") if g.strip()]
    return {
        "id": key,
        "type": rtype,
        "collections": collections,
        "title": latex_to_text(fields.get("title", "")).rstrip("."),
        "authors": parse_names(fields.get("author", "")),
        "editors": parse_names(fields.get("editor", "")),
        "year": _extract_year(fields),
        "container": latex_to_text(container),
        "volume": latex_to_text(fields.get("volume", "")),
        "issue": latex_to_text(fields.get("number") or fields.get("issue", "")),
        "pages": latex_to_text(pages),
        "publisher": latex_to_text(publisher),
        "place": latex_to_text(fields.get("address") or fields.get("location", "")),
        "doi": doi,
        "url": (fields.get("url") or fields.get("howpublished", "")).strip(),
        "edition": latex_to_text(fields.get("edition", "")),
    }


def parse_bibtex(text):
    """Parse BibTeX source text into a list of records."""
    records = []
    strings = {}
    sc = _Scanner(text)
    while True:
        at = sc.text.find("@", sc.pos)
        if at < 0:
            break
        sc.pos = at + 1
        m = re.match(r"[A-Za-z]+", sc.text[sc.pos:])
        if not m:
            continue
        etype = m.group(0)
        sc.pos += len(etype)
        sc.skip_ws()
        if sc.pos >= len(sc.text) or sc.text[sc.pos] not in "{(":
            continue
        open_ch = sc.text[sc.pos]
        close_ch = "}" if open_ch == "{" else ")"
        try:
            body = sc.read_balanced(open_ch, close_ch)
        except ValueError:
            break
        low = etype.lower()
        if low == "comment" or low == "preamble":
            continue
        if low == "string":
            k, fields = None, None
            sm = re.match(r'\s*([A-Za-z0-9_-]+)\s*=', body)
            if sm:
                vsc = _Scanner(body[sm.end():])
                strings[sm.group(1).lower()] = _parse_value(vsc, strings)
            continue
        key, fields = _parse_fields(body, strings)
        if key:
            records.append(_to_record(etype, key, fields))
    return records


def parse_bibtex_file(path):
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return parse_bibtex(f.read())
