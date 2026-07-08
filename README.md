# Mendeley Cite for LibreOffice

[![CI](https://github.com/pedrocandeias/mendeley-libreoffice/actions/workflows/ci.yml/badge.svg)](https://github.com/pedrocandeias/mendeley-libreoffice/actions/workflows/ci.yml)
![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)
![LibreOffice Writer](https://img.shields.io/badge/LibreOffice-Writer-18A303.svg)
![Python](https://img.shields.io/badge/Python-3.x-3776AB.svg)

A LibreOffice Writer extension that brings Mendeley citations to
LibreOffice, similar to the **Mendeley Cite** add-in for Microsoft Word:
search your Mendeley library, insert citations, and generate a formatted
bibliography that renumbers and restyles on refresh.

> **Not affiliated with, endorsed by, or sponsored by Mendeley or
> Elsevier.** "Mendeley" is a trademark of Elsevier; it is used here only
> to describe interoperability. This is an independent, unofficial
> project.

## Overview

Mendeley Cite for LibreOffice puts your reference library where your
writing happens. If you've used the Mendeley Cite add-in for Microsoft
Word, you already know the workflow — this brings that same experience to
LibreOffice Writer, which has never had an official Mendeley integration
of its own.

Instead of copying references by hand or juggling a separate citation
window, you write, place your cursor, and pull citations straight from
your Mendeley library through a searchable picker. Filter by any Mendeley
folder to narrow a large library down to the collection you're actually
drawing from, select one or several references at once, and add page
numbers or a prefix like "see" when you need them. The bibliography at
the end of your document is generated for you and stays in sync: add,
move, or delete a citation and a single Refresh renumbers everything,
re-sorts the reference list, and re-formats every entry.

It fits how researchers actually work. You can connect directly to your
Mendeley account over the official API and sync your library — including
its folder structure — or, if you'd rather not deal with API
credentials, point it at a BibTeX file exported from Mendeley and work
entirely offline. Five citation styles are built in — APA 7th, Harvard,
Chicago 17th author-date, IEEE, and Vancouver — covering both
author-date and numbered conventions, with automatic 2020a/2020b
disambiguation and citation-range collapsing handled the way each style
expects.

Because every citation carries a snapshot of its own reference data
embedded in the document, your files stay refreshable and portable even
when the original library isn't at hand — and switching a finished
manuscript from one style to another is a single menu click. It's a
lightweight, dependency-free extension: install the `.oxt`, and a
Mendeley menu appears in Writer.

## Features

- **Mendeley menu and toolbar in Writer**: Insert Citation, Insert
  Bibliography, Refresh, Settings.
- **Two library sources**
  - **BibTeX file** exported from Mendeley Reference Manager
    (*File → Export All → BibTeX*). Works offline, no API keys needed —
    this is the recommended way to start.
  - **Mendeley REST API**: sign in with OAuth2 and sync your library
    directly. Requires your *own* API application (client ID/secret) —
    see [Getting Mendeley API credentials](#getting-mendeley-api-credentials).
- **Built-in citation styles**: APA 7, Harvard (Cite Them Right),
  Chicago 17th author-date, IEEE, Vancouver.
- **Live document model, like Mendeley in Word**: each citation is a
  reference mark whose name embeds the cited records (compressed JSON),
  so documents remain refreshable even without the library at hand.
  Numeric styles renumber by order of appearance; author-date styles get
  automatic `2020a`/`2020b` disambiguation; page locators, prefixes and
  suffixes are supported; the bibliography lives in a named text section
  and is rebuilt on every refresh.

## Install

```sh
./build.sh
unopkg add --force dist/mendeley-libreoffice.oxt   # or Tools > Extensions > Add
```

For the **snap** build of LibreOffice (where `unopkg` is not on PATH):

```sh
./build.sh
snap run --shell libreoffice <<'EOF'
"$SNAP/lib/libreoffice/program/unopkg" add --force \
    "$HOME/dev/mendeley-libreoffice/dist/mendeley-libreoffice.oxt"
EOF
```

(or simply use *Tools → Extensions… → Add* and pick the `.oxt`).

Restart LibreOffice afterwards. A **Mendeley** menu appears in Writer.

Prefer a prebuilt package? Download the latest `.oxt` from the
[Releases](https://github.com/pedrocandeias/mendeley-libreoffice/releases)
page — no need to build it yourself.

Requires a LibreOffice build with Python scripting support (the default
on Linux distributions and the TDF builds; on Debian/Ubuntu install
`libreoffice-script-provider-python` if the menu items do nothing).

## Usage

1. **Mendeley → Settings…** — pick a citation style and a library
   source:
   - *BibTeX*: browse to the `.bib` file you exported from Mendeley
     Reference Manager. Re-export whenever your library changes; the
     file is re-read on every use.
   - *API*: enter your client ID/secret, then **Sign in & sync**. Your
     browser opens for the Mendeley login; the library is cached locally.
     Use **Sync now** later to pull changes.
2. Place the cursor in your text and use **Mendeley → Insert
   Citation…** — type to filter, pick a **collection** from the
   dropdown to browse just that folder of your library, Ctrl-click for
   multiple works, and optionally add page numbers or a prefix
   (e.g. “see”). Collections come from your Mendeley folders when using
   the API source, or from the `mendeley-groups` BibTeX field when
   present (Mendeley Desktop exports it; Reference Manager currently
   does not).
3. **Mendeley → Insert Bibliography** at the end of the document.
4. **Mendeley → Refresh Citations and Bibliography** after adding,
   moving or deleting citations, or after changing the style.

Configuration, OAuth tokens and the library cache are stored in
`~/.config/mendeley-libreoffice/`.

## Getting Mendeley API credentials

The Mendeley API requires every application to identify itself with a
client ID and secret, and Mendeley/Elsevier does not publish shared
credentials for third-party plugins — so you register your own (free)
app once. The Settings dialog has a **How to get credentials…** button
with the same steps:

1. Go to <https://dev.mendeley.com> (the Mendeley developer portal).
2. Sign in with your Mendeley / Elsevier account.
3. Open **My Apps** → **Register a new app**.
4. Enter any name and description. Set the **redirect URL** to
   `http://localhost:8123`.
5. **Generate a client secret**, save the app, and note the **app ID**
   (this is the client ID — a short number) and the secret.
   In the extension's Settings, the **Redirect URI** field must match
   the redirect URL you registered *character for character* — even a
   missing or extra trailing slash makes Mendeley reject the sign-in
   with "Redirection URI does not match".
6. In Writer: *Mendeley → Settings…*, choose the API source, enter both
   values and click **Sign in & sync**. Your browser opens to authorize
   access; afterwards the library is cached locally and **Sync now**
   pulls updates.

> **If registration is unavailable**: Elsevier has at times closed the
> developer portal to new app registrations. In that case use the
> BibTeX source instead — in Mendeley Reference Manager choose
> *File → Export All → BibTeX* and point the extension at the exported
> file. You get the same citation features; just re-export when your
> library changes.

## Development

```
src/
  description.xml         extension metadata
  META-INF/manifest.xml   registers the Python component and Addons.xcu
  Addons.xcu              Mendeley menu + toolbar
  ProtocolHandler.xcu     routes org.mendeley.lo:* URLs to the component
  python/mendeley_lo.py   UNO protocol handler (org.mendeley.lo:*)
  python/pythonpath/mlo/  pure-Python core + UNO glue
    bibtex.py             BibTeX parser (no dependencies)
    styles.py             citation style renderers
    engine.py             ordering, numbering, disambiguation
    mendeley_api.py       OAuth2 + document fetch (stdlib only)
    config.py             config/tokens/library storage
    document.py           reference marks, bibliography section, refresh
    dialogs.py            runtime-built UNO dialogs
    actions.py            menu command implementations
```

Run the tests (pure-Python core; no LibreOffice needed):

```sh
python3 -m unittest discover -s tests
python3 scripts/demo.py     # render the sample library in every style
```

`scripts/uno_smoke.py` exercises the UNO document layer (marks,
bibliography section, refresh/restyle) against a real headless
LibreOffice listening on a UNO socket — see the script header for how
to launch it.

## Known limitations

- Bibliography entries are rendered as plain text — no italic journal
  or book titles yet.
- Citations inside footnotes/frames refresh correctly but sort after
  body citations for numbering purposes.
- The five styles cover the common cases but are not full CSL; styles
  live in `src/python/pythonpath/mlo/styles.py` and are easy to extend.
- Documents are interoperable with themselves, not with the Word
  plugin's field codes (Word ↔ LibreOffice round-tripping is out of
  scope for now).

## Contributing

Issues and pull requests are welcome. The citation engine, BibTeX parser
and style renderers are pure Python with no LibreOffice dependency, so
they can be developed and tested from the command line (`python3 -m
unittest discover -s tests`). New citation styles are self-contained
classes in `src/python/pythonpath/mlo/styles.py`.

## Releases

Continuous integration runs the test suite and builds the `.oxt` on
every push. To cut a release, bump the version in **both**
`src/description.xml` and `src/python/pythonpath/mlo/__init__.py`, then
push a matching tag:

```sh
git tag v0.2.0
git push origin v0.2.0
```

The release workflow verifies the tag matches those versions, rebuilds
the extension, and publishes a GitHub release with the `.oxt` attached.

## License

Released under the [MIT License](LICENSE).
