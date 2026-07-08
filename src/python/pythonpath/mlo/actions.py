"""Menu command implementations (called by the protocol handler)."""

from . import config, dialogs, document, engine, styles
from . import __version__, DISPLAY_NAME


def _doc(frame):
    doc = frame.getController().getModel()
    if not doc.supportsService("com.sun.star.text.TextDocument"):
        raise RuntimeError("Mendeley citations only work in Writer "
                           "text documents.")
    return doc


def _open_browser(ctx, url):
    shell = ctx.getServiceManager().createInstanceWithContext(
        "com.sun.star.system.SystemShellExecute", ctx)
    shell.execute(url, "", 0)


def _current_style():
    return styles.get_style(config.load_config().get("style", "apa"))


def _load_library_or_setup(ctx, frame):
    """Load the library; on failure walk the user through Settings once."""
    try:
        return config.load_library(config.load_config())
    except Exception:
        dialogs.message_box(
            ctx, frame,
            "No reference library is set up yet.\n\n"
            "In the next dialog, either pick a BibTeX file exported from "
            "Mendeley Reference Manager (File > Export All > BibTeX) or "
            "sign in to the Mendeley API.")
    settings(ctx, frame)
    try:
        return config.load_library(config.load_config())
    except Exception as e:
        dialogs.error_box(ctx, frame, e)
        return None


def insert_citation(ctx, frame):
    doc = _doc(frame)
    records = _load_library_or_setup(ctx, frame)
    if records is None:
        return
    items = dialogs.insert_citation_dialog(ctx, records)
    if not items:
        return
    cluster = {"items": items}
    # Render with only this cluster first for the inserted text, then do
    # a full refresh so numbering/disambiguation stay consistent.
    rendered, _ = engine.process([cluster], _current_style())
    document.insert_citation_mark(doc, cluster, rendered[0])
    document.refresh_document(doc, _current_style(), records)


def insert_bibliography(ctx, frame):
    doc = _doc(frame)
    document.insert_bibliography_section(doc)
    try:
        cfg = config.load_config()
        records = config.load_library(cfg)
    except Exception:
        records = None
    document.refresh_document(doc, _current_style(), records)


def refresh(ctx, frame):
    doc = _doc(frame)
    try:
        records = config.load_library(config.load_config())
    except Exception:
        records = None   # fall back to snapshots stored in the marks
    count, bib = document.refresh_document(doc, _current_style(), records)
    msg = "Updated %d citation%s." % (count, "" if count == 1 else "s")
    if not bib:
        msg += ("\nNo bibliography section found — use Mendeley > "
                "Insert Bibliography to add one.")
    dialogs.message_box(ctx, frame, msg)


def settings(ctx, frame):
    cfg = config.load_config()

    def sync_bibtex(path):
        from . import bibtex
        return len(bibtex.parse_bibtex_file(path))

    def sync_api(candidate_cfg, interactive):
        records = config.sync_api_library(
            candidate_cfg, interactive=interactive,
            open_browser=lambda url: _open_browser(ctx, url))
        return len(records)

    new_cfg = dialogs.settings_dialog(
        ctx, frame, cfg, styles.STYLES, sync_bibtex, sync_api,
        open_url_fn=lambda url: _open_browser(ctx, url))
    if new_cfg is not None:
        config.save_config(new_cfg)


def about(ctx, frame):
    dialogs.message_box(
        ctx, frame,
        "%s %s\n\nInsert and format citations from your Mendeley library "
        "in LibreOffice Writer.\n\nData sources: Mendeley REST API or a "
        "BibTeX export from Mendeley Reference Manager.\nStyles: %s."
        % (DISPLAY_NAME, __version__,
           ", ".join(s.name for s in styles.STYLES)),
        "About Mendeley Cite")


COMMANDS = {
    "InsertCitation": insert_citation,
    "InsertBibliography": insert_bibliography,
    "Refresh": refresh,
    "Settings": settings,
    "About": about,
}


def dispatch(ctx, frame, command):
    fn = COMMANDS.get(command)
    if fn is None:
        raise RuntimeError("Unknown Mendeley command: %r" % command)
    try:
        fn(ctx, frame)
    except Exception as e:
        dialogs.error_box(ctx, frame, e)
