"""Built-in citation styles (plain-text rendering).

Each style renders in-text citation clusters and bibliography entries
from the internal record format (see bibtex.py).

Two kinds of style:
  * author-date  — (Smith, 2020, p. 4); bibliography sorted alphabetically
  * numeric      — [1] / (1); bibliography sorted by first appearance

Rendering is plain text (no italics) because citations live inside
reference-mark text runs; this matches what most reviewers need and
keeps refresh robust.
"""

import re

EN_DASH = "–"


# ---------------------------------------------------------------- helpers

def _initials(given, dot=True, space=True):
    """'John Ronald' -> 'J. R.' (dot/space configurable)."""
    parts = [p for p in re.split(r"[\s.]+", given.strip()) if p]
    out = []
    for p in parts:
        subs = p.split("-")
        ini = "-".join(s[0].upper() + ("." if dot else "") for s in subs if s)
        out.append(ini)
    return (" " if space else "").join(out)


def _pages_dash(pages):
    return re.sub(r"\s*-+\s*", EN_DASH, pages or "")


def _clean_join(parts, sep=" "):
    """Join non-empty segments, collapsing duplicate terminal punctuation."""
    out = ""
    for p in parts:
        p = (p or "").strip()
        if not p:
            continue
        if out:
            if out[-1] in ".,:;?!" and p[0] in ".,":
                p = p[1:].strip()
            if not p:
                continue
            out += sep + p
        else:
            out = p
    return out


def _sentence(s):
    """Ensure a segment ends with a period (unless ?/!)."""
    s = (s or "").strip()
    if s and s[-1] not in ".?!":
        s += "."
    return s


def _year_str(rec, suffix=""):
    y = rec.get("year")
    return (str(y) + suffix) if y else ("n.d." + suffix)


def _first_family(rec):
    a = rec.get("authors") or rec.get("editors") or []
    if a:
        return a[0]["family"]
    return rec.get("title") or ""


def _doi_or_url(rec, doi_prefix="https://doi.org/"):
    if rec.get("doi"):
        return doi_prefix + rec["doi"]
    return rec.get("url") or ""


def _locator_text(locator, style="pp"):
    """Format a user-entered locator like '12' or '12-14'."""
    loc = (locator or "").strip()
    if not loc:
        return ""
    loc = _pages_dash(loc)
    if style == "none":
        return loc
    plural = EN_DASH in loc or "," in loc
    return ("pp. " if plural else "p. ") + loc


# ---------------------------------------------------------------- base

class Style(object):
    id = ""
    name = ""
    kind = "author-date"          # or "numeric"

    # --- author-date knobs (overridden per style)
    two_author_sep = " & "        # between exactly two in-text names
    etal_min = 3                  # >= this many authors -> "First et al."
    etal_show = 1
    year_sep = ", "               # between names and year in citation
    locator_sep = ", "
    locator_style = "pp"          # "pp" -> p./pp. prefix; "none" -> bare

    def sort_key(self, rec):
        fam = _first_family(rec).lower()
        return (fam, rec.get("year") or 9999, (rec.get("title") or "").lower())

    # ---- in-text -------------------------------------------------------
    def short_names(self, rec):
        names = rec.get("authors") or rec.get("editors") or []
        if not names:
            t = (rec.get("title") or "Anon").strip()
            return ('"%s"' % t) if len(t) <= 30 else ('"%s..."' % t[:27])
        fams = [n["family"] for n in names]
        if len(fams) >= self.etal_min:
            shown = fams[:self.etal_show]
            return ", ".join(shown) + " et al."
        if len(fams) == 1:
            return fams[0]
        if len(fams) == 2:
            return fams[0] + self.two_author_sep + fams[1]
        return ", ".join(fams[:-1]) + self.two_author_sep + fams[-1]

    def citation(self, items):
        """items: [{'rec','locator','prefix','suffix','year_suffix'}]"""
        parts = []
        for it in items:
            rec = it["rec"]
            seg = self.short_names(rec) + self.year_sep + \
                _year_str(rec, it.get("year_suffix", ""))
            loc = _locator_text(it.get("locator"), self.locator_style)
            if loc:
                seg += self.locator_sep + loc
            if it.get("prefix"):
                seg = it["prefix"].rstrip() + " " + seg
            if it.get("suffix"):
                seg += ", " + it["suffix"].lstrip(", ")
            parts.append(seg)
        return "(" + "; ".join(parts) + ")"

    # ---- bibliography ---------------------------------------------------
    def entry(self, rec, year_suffix="", number=None):
        t = rec.get("type", "generic")
        fn = getattr(self, "entry_" + t.replace("-", "_"), None)
        if fn is None:
            fn = self.entry_generic
        return fn(rec, year_suffix)


# ---------------------------------------------------------------- APA 7

class APA(Style):
    id = "apa"
    name = "APA 7th edition"
    two_author_sep = " & "
    etal_min = 3

    def _names(self, names):
        fmt = ["%s, %s" % (n["family"], _initials(n["given"]))
               if n["given"] else n["family"] for n in names]
        if not fmt:
            return ""
        if len(fmt) == 1:
            return fmt[0]
        if len(fmt) <= 20:
            return ", ".join(fmt[:-1]) + ", & " + fmt[-1]
        return ", ".join(fmt[:19]) + ", ... " + fmt[-1]

    def _head(self, rec, ys):
        names = self._names(rec.get("authors") or [])
        year = "(%s)." % _year_str(rec, ys)
        if not names:
            return _clean_join([_sentence(rec.get("title", "")), year])
        return _clean_join([_sentence(names), year])

    def _title_after_head(self, rec):
        return "" if not rec.get("authors") else _sentence(rec.get("title", ""))

    def entry_article_journal(self, rec, ys=""):
        src = _clean_join([
            rec.get("container", "") + ",",
            (rec.get("volume", "") +
             ("(%s)" % rec["issue"] if rec.get("issue") else "") + ","
             if rec.get("volume") else ""),
            _sentence(_pages_dash(rec.get("pages", ""))),
        ])
        return _clean_join([self._head(rec, ys), self._title_after_head(rec),
                            src, _doi_or_url(rec)])

    def entry_book(self, rec, ys=""):
        title = rec.get("title", "")
        if rec.get("edition"):
            title += " (%s ed.)" % rec["edition"]
        return _clean_join([self._head(rec, ys),
                            _sentence(title) if rec.get("authors") else "",
                            _sentence(rec.get("publisher", "")),
                            _doi_or_url(rec)])

    def _names_given_first(self, names):
        fmt = [(_initials(n["given"]) + " " + n["family"]).strip()
               for n in names]
        if not fmt:
            return ""
        if len(fmt) == 1:
            return fmt[0]
        if len(fmt) == 2:
            return fmt[0] + " & " + fmt[1]
        return ", ".join(fmt[:-1]) + ", & " + fmt[-1]

    def entry_chapter(self, rec, ys=""):
        eds = self._names_given_first(rec.get("editors") or [])
        eds_label = " (Ed.)," if len(rec.get("editors") or []) == 1 \
            else " (Eds.),"
        inpart = "In " + _clean_join([
            (eds + eds_label if eds else ""),
            rec.get("container", ""),
            ("(pp. %s)." % _pages_dash(rec["pages"]) if rec.get("pages") else ""),
        ])
        if not inpart.rstrip().endswith("."):
            inpart = _sentence(inpart)
        return _clean_join([self._head(rec, ys), self._title_after_head(rec),
                            inpart, _sentence(rec.get("publisher", "")),
                            _doi_or_url(rec)])

    entry_paper_conference = entry_chapter

    def entry_thesis(self, rec, ys=""):
        return _clean_join([self._head(rec, ys),
                            _sentence(rec.get("title", "") + " [Thesis]")
                            if rec.get("authors") else "",
                            _sentence(rec.get("publisher", "")),
                            _doi_or_url(rec)])

    def entry_report(self, rec, ys=""):
        return _clean_join([self._head(rec, ys), self._title_after_head(rec),
                            _sentence(rec.get("publisher", "")),
                            _doi_or_url(rec)])

    def entry_webpage(self, rec, ys=""):
        return _clean_join([self._head(rec, ys), self._title_after_head(rec),
                            _sentence(rec.get("container") or rec.get("publisher", "")),
                            rec.get("url") or _doi_or_url(rec)])

    entry_generic = entry_report


# ---------------------------------------------------------------- Harvard

class Harvard(Style):
    id = "harvard"
    name = "Harvard (Cite Them Right)"
    two_author_sep = " and "
    etal_min = 4

    def _names(self, names):
        fmt = ["%s, %s" % (n["family"], _initials(n["given"], space=False))
               if n["given"] else n["family"] for n in names]
        if not fmt:
            return ""
        if len(fmt) >= 4:
            return fmt[0] + " et al."
        if len(fmt) == 1:
            return fmt[0]
        return ", ".join(fmt[:-1]) + " and " + fmt[-1]

    def _head(self, rec, ys):
        names = self._names(rec.get("authors") or [])
        year = "(%s)" % _year_str(rec, ys)
        return _clean_join([names or _sentence(rec.get("title", "")), year])

    def entry_article_journal(self, rec, ys=""):
        vol = rec.get("volume", "")
        if rec.get("issue"):
            vol += "(%s)" % rec["issue"]
        tail = "doi:%s." % rec["doi"] if rec.get("doi") else ""
        return _clean_join([self._head(rec, ys),
                            "'%s'," % rec.get("title", ""),
                            rec.get("container", "") + ",",
                            (vol + "," if vol else ""),
                            _sentence("pp. " + _pages_dash(rec["pages"]))
                            if rec.get("pages") else "",
                            tail])

    def entry_book(self, rec, ys=""):
        parts = [self._head(rec, ys), _sentence(rec.get("title", ""))]
        if rec.get("edition"):
            parts.append("%s edn." % rec["edition"])
        pp = _clean_join([rec.get("place", "") + ":" if rec.get("place") else "",
                          rec.get("publisher", "")])
        parts.append(_sentence(pp))
        return _clean_join(parts)

    def entry_chapter(self, rec, ys=""):
        eds = self._names(rec.get("editors") or [])
        pp = _clean_join([rec.get("place", "") + ":" if rec.get("place") else "",
                          rec.get("publisher", "")])
        return _clean_join([
            self._head(rec, ys),
            "'%s'," % rec.get("title", ""),
            "in " + (eds + " (eds) " if eds else "") + _sentence(rec.get("container", "")),
            (pp + "," if rec.get("pages") else _sentence(pp)),
            _sentence("pp. " + _pages_dash(rec["pages"])) if rec.get("pages") else "",
        ])

    entry_paper_conference = entry_chapter

    def entry_webpage(self, rec, ys=""):
        tail = "Available at: %s." % rec["url"] if rec.get("url") else ""
        return _clean_join([self._head(rec, ys),
                            _sentence(rec.get("title", "")), tail])

    def entry_generic(self, rec, ys=""):
        return _clean_join([self._head(rec, ys),
                            _sentence(rec.get("title", "")),
                            _sentence(rec.get("publisher", "")),
                            _doi_or_url(rec)])

    entry_thesis = entry_generic
    entry_report = entry_generic


# ---------------------------------------------------------------- Chicago

class ChicagoAD(Style):
    id = "chicago-ad"
    name = "Chicago 17th (author-date)"
    two_author_sep = " and "
    etal_min = 4
    year_sep = " "
    locator_style = "none"

    def _names(self, names, invert_first=True):
        fmt = []
        for i, n in enumerate(names):
            if i == 0 and invert_first:
                fmt.append("%s, %s" % (n["family"], n["given"])
                           if n["given"] else n["family"])
            else:
                fmt.append((n["given"] + " " + n["family"]).strip())
        if not fmt:
            return ""
        if len(fmt) > 10:
            return ", ".join(fmt[:7]) + ", et al."
        if len(fmt) == 1:
            return fmt[0]
        if len(fmt) == 2:
            return fmt[0] + ", and " + fmt[1] if invert_first \
                else fmt[0] + " and " + fmt[1]
        return ", ".join(fmt[:-1]) + ", and " + fmt[-1]

    def _head(self, rec, ys):
        names = self._names(rec.get("authors") or [])
        return _clean_join([_sentence(names) if names
                            else _sentence('"%s"' % rec.get("title", "")),
                            _sentence(_year_str(rec, ys))])

    def entry_article_journal(self, rec, ys=""):
        src = rec.get("container", "")
        if rec.get("volume"):
            src += " " + rec["volume"]
        if rec.get("issue"):
            src += " (%s)" % rec["issue"]
        if rec.get("pages"):
            src += ": " + _pages_dash(rec["pages"])
        return _clean_join([self._head(rec, ys),
                            '"%s."' % rec.get("title", "")
                            if rec.get("authors") else "",
                            _sentence(src), _doi_or_url(rec)])

    def entry_book(self, rec, ys=""):
        pp = _clean_join([rec.get("place", "") + ":" if rec.get("place") else "",
                          rec.get("publisher", "")])
        return _clean_join([self._head(rec, ys),
                            _sentence(rec.get("title", ""))
                            if rec.get("authors") else "",
                            _sentence(pp)])

    def entry_chapter(self, rec, ys=""):
        eds = self._names(rec.get("editors") or [], invert_first=False)
        src = "In " + rec.get("container", "")
        if eds:
            src += ", edited by " + eds
        if rec.get("pages"):
            src += ", " + _pages_dash(rec["pages"])
        pp = _clean_join([rec.get("place", "") + ":" if rec.get("place") else "",
                          rec.get("publisher", "")])
        return _clean_join([self._head(rec, ys),
                            '"%s."' % rec.get("title", "")
                            if rec.get("authors") else "",
                            _sentence(src), _sentence(pp)])

    entry_paper_conference = entry_chapter
    entry_generic = entry_book
    entry_thesis = entry_book
    entry_report = entry_book

    def entry_webpage(self, rec, ys=""):
        return _clean_join([self._head(rec, ys),
                            '"%s."' % rec.get("title", "")
                            if rec.get("authors") else "",
                            _sentence(rec.get("container") or rec.get("publisher", "")),
                            rec.get("url", "")])


# ---------------------------------------------------------------- IEEE

class IEEE(Style):
    id = "ieee"
    name = "IEEE"
    kind = "numeric"
    bracket = ("[", "]")
    collapse = True

    def _names(self, names, etal_after=6):
        fmt = [(_initials(n["given"]) + " " + n["family"]).strip()
               for n in names]
        if not fmt:
            return ""
        if len(fmt) > etal_after:
            return fmt[0] + " et al."
        if len(fmt) == 1:
            return fmt[0]
        if len(fmt) == 2:
            return fmt[0] + " and " + fmt[1]
        return ", ".join(fmt[:-1]) + ", and " + fmt[-1]

    def citation(self, items):
        return render_numeric_cluster(items, self.bracket, ", ",
                                      self.collapse, loc_fmt="%s, %s")

    def entry(self, rec, year_suffix="", number=None):
        body = self._entry_body(rec)
        return "[%d] %s" % (number, body) if number else body

    def _entry_body(self, rec):
        t = rec.get("type", "generic")
        names = self._names(rec.get("authors") or [])
        if t == "article-journal":
            segs = [names + "," if names else "",
                    '"%s,"' % rec.get("title", ""),
                    rec.get("container", "") + ",",
                    "vol. %s," % rec["volume"] if rec.get("volume") else "",
                    "no. %s," % rec["issue"] if rec.get("issue") else "",
                    "pp. %s," % _pages_dash(rec["pages"]) if rec.get("pages") else "",
                    _sentence(_year_str(rec)),
                    "doi: %s." % rec["doi"] if rec.get("doi") else ""]
        elif t in ("paper-conference", "chapter"):
            segs = [names + "," if names else "",
                    '"%s,"' % rec.get("title", ""),
                    "in " + rec.get("container", "") + ",",
                    _year_str(rec) + ",",
                    _sentence("pp. " + _pages_dash(rec["pages"]))
                    if rec.get("pages") else _sentence(""),
                    ]
        elif t == "book":
            segs = [names + "," if names else "",
                    rec.get("title", "") + ",",
                    "%s ed." % rec["edition"] if rec.get("edition") else "",
                    (rec.get("place", "") + ":" if rec.get("place") else ""),
                    rec.get("publisher", "") + "," if rec.get("publisher") else "",
                    _sentence(_year_str(rec))]
        elif t == "webpage":
            segs = [names + "," if names else "",
                    '"%s,"' % rec.get("title", ""),
                    rec.get("container") or rec.get("publisher", ""),
                    _sentence(_year_str(rec)),
                    "[Online]. Available: " + rec["url"] if rec.get("url") else ""]
        else:
            segs = [names + "," if names else "",
                    '"%s,"' % rec.get("title", ""),
                    rec.get("publisher", "") + "," if rec.get("publisher") else "",
                    _sentence(_year_str(rec)),
                    "doi: %s." % rec["doi"] if rec.get("doi") else ""]
        return _clean_join(segs)


# ---------------------------------------------------------------- Vancouver

class Vancouver(Style):
    id = "vancouver"
    name = "Vancouver"
    kind = "numeric"
    bracket = ("(", ")")
    collapse = True

    def _names(self, names):
        fmt = [(n["family"] + " " +
                _initials(n["given"], dot=False, space=False)).strip()
               for n in names]
        if not fmt:
            return ""
        if len(fmt) > 6:
            return ", ".join(fmt[:6]) + ", et al."
        return ", ".join(fmt)

    def citation(self, items):
        return render_numeric_cluster(items, self.bracket, ",",
                                      self.collapse, loc_fmt="%s, %s")

    def entry(self, rec, year_suffix="", number=None):
        body = self._entry_body(rec)
        return "%d. %s" % (number, body) if number else body

    def _entry_body(self, rec):
        t = rec.get("type", "generic")
        names = _sentence(self._names(rec.get("authors") or []))
        title = _sentence(rec.get("title", ""))
        if t == "article-journal":
            src = _sentence(rec.get("container", ""))
            tail = _year_str(rec)
            if rec.get("volume"):
                tail += ";" + rec["volume"]
                if rec.get("issue"):
                    tail += "(%s)" % rec["issue"]
            if rec.get("pages"):
                tail += ":" + rec["pages"].replace(EN_DASH, "-")
            return _clean_join([names, title, src, _sentence(tail)])
        if t == "book":
            pp = _clean_join([rec.get("place", "") + ":" if rec.get("place") else "",
                              rec.get("publisher", "") + ";" if rec.get("publisher") else "",
                              _year_str(rec)])
            ed = "%s ed." % rec["edition"] if rec.get("edition") else ""
            return _clean_join([names, title, ed, _sentence(pp)])
        if t in ("chapter", "paper-conference"):
            eds = self._names(rec.get("editors") or [])
            src = "In: " + _clean_join([eds + ", editors." if eds else "",
                                        _sentence(rec.get("container", ""))])
            pp = _clean_join([rec.get("place", "") + ":" if rec.get("place") else "",
                              rec.get("publisher", "") + ";" if rec.get("publisher") else "",
                              _year_str(rec) + "." if rec.get("year") else "",
                              "p. " + rec.get("pages", "").replace(EN_DASH, "-") + "."
                              if rec.get("pages") else ""])
            return _clean_join([names, title, _sentence(src), pp])
        if t == "webpage":
            tail = "Available from: %s" % rec["url"] if rec.get("url") else ""
            return _clean_join([names, title,
                                _sentence(rec.get("container")
                                          or rec.get("publisher", "")),
                                _sentence(_year_str(rec)), tail])
        return _clean_join([names, title,
                            _sentence(rec.get("publisher", "")),
                            _sentence(_year_str(rec))])


# ---------------------------------------------------------------- numeric shared

def render_numeric_cluster(items, bracket, sep, collapse, loc_fmt="%s, %s"):
    """Render e.g. [1]-[3], [5] or (1-3,5); locators disable collapsing."""
    open_b, close_b = bracket
    if any(it.get("locator") for it in items):
        segs = []
        for it in items:
            n = str(it["number"])
            loc = _locator_text(it.get("locator"))
            segs.append(open_b + (loc_fmt % (n, loc) if loc else n) + close_b)
        return sep.join(segs)
    nums = sorted(set(it["number"] for it in items))
    groups = []
    start = prev = nums[0]
    for n in nums[1:]:
        if n == prev + 1:
            prev = n
            continue
        groups.append((start, prev))
        start = prev = n
    groups.append((start, prev))
    if open_b == "[":
        # IEEE: each number individually bracketed
        segs = []
        for a, b in groups:
            if b - a >= 2:
                segs.append("[%d]%s[%d]" % (a, EN_DASH, b))
            elif b == a + 1:
                segs.append("[%d], [%d]" % (a, b))
            else:
                segs.append("[%d]" % a)
        return ", ".join(segs)
    segs = []
    for a, b in groups:
        if b - a >= 2:
            segs.append("%d%s%d" % (a, EN_DASH, b))
        elif b == a + 1:
            segs.append("%d,%d" % (a, b))
        else:
            segs.append("%d" % a)
    return open_b + sep.join(segs) + close_b


# ---------------------------------------------------------------- registry

STYLES = [APA(), Harvard(), ChicagoAD(), IEEE(), Vancouver()]
STYLE_MAP = dict((s.id, s) for s in STYLES)
DEFAULT_STYLE = "apa"


def get_style(style_id):
    return STYLE_MAP.get(style_id) or STYLE_MAP[DEFAULT_STYLE]
