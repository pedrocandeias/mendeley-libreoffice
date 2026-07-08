"""Configuration, token and library-cache storage.

Everything lives in ~/.config/mendeley-libreoffice/ (or
$XDG_CONFIG_HOME/mendeley-libreoffice/):

    config.json   — data source, API credentials, chosen style
    tokens.json   — OAuth tokens (chmod 600)
    library.json  — cached records fetched from the Mendeley API
"""

import json
import os

DEFAULTS = {
    "source": "bibtex",          # "bibtex" | "api"
    "bibtex_path": "",
    "client_id": "",
    "client_secret": "",
    "redirect_uri": "http://localhost:8123/",
    "style": "apa",
}


def config_dir():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(
        os.path.expanduser("~"), ".config")
    d = os.path.join(base, "mendeley-libreoffice")
    os.makedirs(d, exist_ok=True)
    return d


def _path(name):
    return os.path.join(config_dir(), name)


def _load_json(name, default):
    try:
        with open(_path(name), "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _save_json(name, data, private=False):
    p = _path(name)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    if private:
        try:
            os.chmod(p, 0o600)
        except OSError:
            pass


def load_config():
    cfg = dict(DEFAULTS)
    stored = _load_json("config.json", {})
    cfg.update(stored)
    # Migrate pre-0.1 configs that stored only a port.
    if "redirect_uri" not in stored and stored.get("redirect_port"):
        cfg["redirect_uri"] = "http://localhost:%s/" % stored["redirect_port"]
    return cfg


def save_config(cfg):
    _save_json("config.json", cfg)


def load_tokens():
    return _load_json("tokens.json", {})


def save_tokens(tokens):
    _save_json("tokens.json", tokens, private=True)


def load_cached_library():
    return _load_json("library.json", {}).get("records", [])


def save_cached_library(records):
    _save_json("library.json", {"records": records})


def load_library(cfg):
    """Return the reference library as a list of records.

    bibtex source: parse the configured .bib file (always fresh).
    api source: return the cached copy from the last sync.
    """
    if cfg.get("source") == "bibtex":
        path = cfg.get("bibtex_path", "")
        if not path or not os.path.exists(path):
            raise FileNotFoundError(
                "BibTeX file not found: %r. Set it in Mendeley > Settings.\n"
                "(In Mendeley Reference Manager: File > Export All > BibTeX.)"
                % path)
        from . import bibtex
        return bibtex.parse_bibtex_file(path)
    records = load_cached_library()
    if not records:
        raise RuntimeError(
            "The library cache is empty. Use Mendeley > Settings > "
            "'Sign in & sync' (or 'Sync now') first.")
    return records


def sync_api_library(cfg, interactive=False, open_browser=None):
    """Fetch the library from the Mendeley API into the local cache."""
    from . import mendeley_api
    client = mendeley_api.MendeleyClient(
        cfg.get("client_id", ""), cfg.get("client_secret", ""),
        redirect_uri=cfg.get("redirect_uri", ""),
        tokens=load_tokens(), save_tokens=save_tokens)
    if interactive:
        client.sign_in(open_browser)
    records = client.fetch_library()
    save_cached_library(records)
    return records
