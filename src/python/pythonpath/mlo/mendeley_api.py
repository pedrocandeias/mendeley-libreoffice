"""Mendeley REST API client (stdlib only).

Implements the OAuth2 authorization-code flow against api.mendeley.com
with a temporary localhost HTTP server catching the redirect, plus
paginated document fetching mapped into the internal record format.

You need your own API application (client id/secret) registered at
https://dev.mendeley.com with redirect URI http://localhost:<port>/
— see the README; if registration is unavailable to you, use the
BibTeX data source instead.
"""

import base64
import json
import re
import secrets
import threading
import urllib.parse
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer

# api.mendeley.com is behind Cloudflare, which rejects urllib's default
# User-Agent with a 403 "error code: 1010" — always send a real one.
USER_AGENT = "MendeleyCiteLibreOffice/0.1 (+https://github.com/; LibreOffice extension)"

AUTH_URL = "https://api.mendeley.com/oauth/authorize"
TOKEN_URL = "https://api.mendeley.com/oauth/token"
API_BASE = "https://api.mendeley.com"
DOC_ACCEPT = "application/vnd.mendeley-document.1+json"
FOLDER_ACCEPT = "application/vnd.mendeley-folder.1+json"

DOC_TYPE_MAP = {
    "journal": "article-journal",
    "journal_article": "article-journal",
    "magazine_article": "article-journal",
    "newspaper_article": "article-journal",
    "book": "book",
    "book_section": "chapter",
    "conference_proceedings": "paper-conference",
    "thesis": "thesis",
    "report": "report",
    "working_paper": "report",
    "web_page": "webpage",
    "generic": "generic",
    "patent": "generic",
    "computer_program": "generic",
}


class AuthError(Exception):
    pass


class _RedirectCatcher(BaseHTTPRequestHandler):
    code = None
    state = None

    def do_GET(self):
        q = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(q)
        _RedirectCatcher.code = (params.get("code") or [None])[0]
        _RedirectCatcher.state = (params.get("state") or [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        ok = _RedirectCatcher.code is not None
        msg = ("Signed in to Mendeley. You can close this tab and return "
               "to LibreOffice." if ok else
               "Sign-in failed: no authorization code received.")
        self.wfile.write(("<html><body><h2>%s</h2></body></html>" % msg)
                         .encode("utf-8"))

    def log_message(self, *args):
        pass


class MendeleyClient(object):
    def __init__(self, client_id, client_secret,
                 redirect_uri="http://localhost:8123/",
                 tokens=None, save_tokens=None):
        self.client_id = client_id
        self.client_secret = client_secret
        # Mendeley compares the redirect URI character-for-character with
        # the app registration, so we send exactly what was configured.
        self.redirect_uri = redirect_uri or "http://localhost:8123/"
        parsed = urllib.parse.urlparse(self.redirect_uri)
        self.port = parsed.port or 8123
        self.tokens = tokens or {}
        self.save_tokens = save_tokens or (lambda t: None)

    # ---------------------------------------------------------- OAuth

    def auth_url(self, state):
        return AUTH_URL + "?" + urllib.parse.urlencode({
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": "all",
            "state": state,
        })

    def sign_in(self, open_browser, timeout=180):
        """Run the interactive OAuth flow. Blocks until redirect/timeout."""
        if not self.client_id or not self.client_secret:
            raise AuthError("Client ID and secret are not configured.")
        state = secrets.token_urlsafe(16)
        _RedirectCatcher.code = None
        _RedirectCatcher.state = None
        server = HTTPServer(("127.0.0.1", self.port), _RedirectCatcher)
        server.timeout = 1
        stop = threading.Event()

        def _serve():
            while not stop.is_set() and _RedirectCatcher.code is None:
                server.handle_request()

        thread = threading.Thread(target=_serve, daemon=True)
        thread.start()
        try:
            open_browser(self.auth_url(state))
            thread.join(timeout)
        finally:
            stop.set()
            server.server_close()
        if _RedirectCatcher.code is None:
            raise AuthError("Timed out waiting for the browser sign-in.")
        if _RedirectCatcher.state != state:
            raise AuthError("OAuth state mismatch; aborting.")
        self._token_request({
            "grant_type": "authorization_code",
            "code": _RedirectCatcher.code,
            "redirect_uri": self.redirect_uri,
        })

    def _token_request(self, data):
        body = urllib.parse.urlencode(data).encode("ascii")
        basic = base64.b64encode(
            ("%s:%s" % (self.client_id, self.client_secret)).encode("utf-8")
        ).decode("ascii")
        req = urllib.request.Request(TOKEN_URL, data=body, headers={
            "Authorization": "Basic " + basic,
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": USER_AGENT,
        })
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                self.tokens = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise AuthError("Token request failed (%d): %s"
                            % (e.code, e.read().decode("utf-8", "replace")[:300]))
        self.save_tokens(self.tokens)

    def _refresh(self):
        rt = self.tokens.get("refresh_token")
        if not rt:
            raise AuthError("Not signed in (no refresh token). "
                            "Use 'Sign in' in Mendeley > Settings.")
        self._token_request({"grant_type": "refresh_token",
                             "refresh_token": rt})

    # ---------------------------------------------------------- API

    def _get(self, url, accept=DOC_ACCEPT, retry=True):
        token = self.tokens.get("access_token")
        if not token:
            self._refresh()
            token = self.tokens.get("access_token")
        req = urllib.request.Request(url, headers={
            "Authorization": "Bearer " + token,
            "Accept": accept,
            "User-Agent": USER_AGENT,
        })
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return (json.loads(resp.read().decode("utf-8")),
                        resp.headers.get("Link", ""))
        except urllib.error.HTTPError as e:
            if e.code == 401 and retry:
                self._refresh()
                return self._get(url, accept=accept, retry=False)
            raise AuthError("Mendeley API error (%d): %s"
                            % (e.code, e.read().decode("utf-8", "replace")[:300]))

    def _get_paginated(self, url, accept=DOC_ACCEPT):
        items = []
        while url:
            page, link = self._get(url, accept=accept)
            items.extend(page)
            m = re.search(r'<([^>]+)>;\s*rel="next"', link or "")
            url = m.group(1) if m else None
        return items

    def fetch_all_documents(self):
        """Fetch every document in the user's library as records."""
        url = API_BASE + "/documents?" + urllib.parse.urlencode(
            {"limit": 500, "view": "all", "order": "asc", "sort": "created"})
        return [map_document(d) for d in self._get_paginated(url)]

    def fetch_folders(self):
        """Return {folder_id: full_path_name} for all folders/collections."""
        folders = self._get_paginated(API_BASE + "/folders?limit=200",
                                      accept=FOLDER_ACCEPT)
        by_id = dict((f["id"], f) for f in folders if f.get("id"))

        def path(fid, depth=0):
            f = by_id.get(fid)
            if f is None or depth > 10:      # missing parent / cycle guard
                return ""
            parent = path(f.get("parent_id"), depth + 1) \
                if f.get("parent_id") else ""
            name = f.get("name", "")
            return (parent + " / " + name) if parent else name

        return dict((fid, path(fid)) for fid in by_id)

    def fetch_library(self, progress=None):
        """Fetch documents plus their collection (folder) memberships."""
        records = self.fetch_all_documents()
        by_id = dict((r["id"], r) for r in records)
        try:
            folders = self.fetch_folders()
        except AuthError:
            folders = {}
        for i, (fid, name) in enumerate(sorted(folders.items(),
                                               key=lambda kv: kv[1])):
            if progress:
                progress("Collections %d/%d..." % (i + 1, len(folders)))
            try:
                doc_ids = self._get_paginated(
                    API_BASE + "/folders/%s/documents?limit=500" % fid)
            except AuthError:
                continue
            for d in doc_ids:
                rec = by_id.get(d.get("id"))
                if rec is not None and name:
                    rec.setdefault("collections", []).append(name)
        for r in records:
            r["collections"] = sorted(set(r.get("collections") or []))
        return records


def map_document(d):
    """Map a Mendeley API document JSON object to an internal record."""
    authors = [{"family": a.get("last_name", "") or "",
                "given": a.get("first_name", "") or ""}
               for a in (d.get("authors") or [])]
    editors = [{"family": a.get("last_name", "") or "",
                "given": a.get("first_name", "") or ""}
               for a in (d.get("editors") or [])]
    ids = d.get("identifiers") or {}
    websites = d.get("websites") or []
    return {
        "id": d.get("id", ""),
        "type": DOC_TYPE_MAP.get(d.get("type", ""), "generic"),
        "title": (d.get("title") or "").strip().rstrip("."),
        "authors": authors,
        "editors": editors,
        "year": d.get("year"),
        "container": d.get("source") or "",
        "volume": str(d.get("volume") or ""),
        "issue": str(d.get("issue") or ""),
        "pages": (d.get("pages") or "").replace("--", "-"),
        "publisher": d.get("publisher") or d.get("institution") or "",
        "place": d.get("city") or "",
        "doi": ids.get("doi") or "",
        "url": websites[0] if websites else "",
        "edition": str(d.get("edition") or ""),
        "collections": [],
    }
