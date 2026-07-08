"""Runtime-built UNO dialogs (no .xdl resources needed)."""

import traceback

import uno
import unohelper
from com.sun.star.awt import XActionListener, XItemListener, XTextListener


# ---------------------------------------------------------------- plumbing

def _smgr(ctx):
    return ctx.getServiceManager()


def make_dialog(ctx, title, width, height):
    smgr = _smgr(ctx)
    model = smgr.createInstanceWithContext(
        "com.sun.star.awt.UnoControlDialogModel", ctx)
    model.Width = width
    model.Height = height
    model.Title = title
    model.Closeable = True
    dialog = smgr.createInstanceWithContext(
        "com.sun.star.awt.UnoControlDialog", ctx)
    dialog.setModel(model)
    return dialog, model


def add_control(model, kind, name, x, y, w, h, **props):
    cmodel = model.createInstance("com.sun.star.awt.UnoControl%sModel" % kind)
    cmodel.PositionX = x
    cmodel.PositionY = y
    cmodel.Width = w
    cmodel.Height = h
    cmodel.Name = name
    for k, v in props.items():
        setattr(cmodel, k, v)
    model.insertByName(name, cmodel)
    return cmodel


def show_dialog(ctx, dialog):
    toolkit = _smgr(ctx).createInstanceWithContext(
        "com.sun.star.awt.Toolkit", ctx)
    dialog.createPeer(toolkit, None)
    result = dialog.execute()
    dialog.dispose()
    return result


def _button_type(name):
    return uno.Enum("com.sun.star.awt.PushButtonType", name)


def message_box(ctx, frame, text, title="Mendeley", kind="MESSAGEBOX"):
    toolkit = _smgr(ctx).createInstanceWithContext(
        "com.sun.star.awt.Toolkit", ctx)
    parent = frame.getContainerWindow() if frame else None
    box = toolkit.createMessageBox(
        parent, uno.Enum("com.sun.star.awt.MessageBoxType", kind),
        1,  # MessageBoxButtons.BUTTONS_OK
        title, str(text))
    box.execute()


def error_box(ctx, frame, exc, title="Mendeley — error"):
    detail = "".join(traceback.format_exception_only(type(exc), exc)).strip()
    message_box(ctx, frame, detail, title, "ERRORBOX")


class _Action(unohelper.Base, XActionListener):
    def __init__(self, fn):
        self.fn = fn

    def actionPerformed(self, event):
        try:
            self.fn()
        except Exception:
            traceback.print_exc()

    def disposing(self, event):
        pass


class _ItemChange(unohelper.Base, XItemListener):
    def __init__(self, fn):
        self.fn = fn

    def itemStateChanged(self, event):
        try:
            self.fn()
        except Exception:
            traceback.print_exc()

    def disposing(self, event):
        pass


class _TextChange(unohelper.Base, XTextListener):
    def __init__(self, fn):
        self.fn = fn

    def textChanged(self, event):
        try:
            self.fn()
        except Exception:
            traceback.print_exc()

    def disposing(self, event):
        pass


# ---------------------------------------------------------------- insert citation

def _record_label(rec):
    fams = ", ".join(n["family"] for n in (rec.get("authors") or [])[:3])
    if len(rec.get("authors") or []) > 3:
        fams += " et al."
    year = rec.get("year") or "n.d."
    title = rec.get("title") or "(untitled)"
    if len(title) > 70:
        title = title[:67] + "..."
    return "%s (%s) — %s" % (fams or "(no author)", year, title)


def _matches(rec, query):
    hay = " ".join([
        " ".join(n["family"] + " " + n["given"]
                 for n in (rec.get("authors") or [])),
        str(rec.get("year") or ""),
        rec.get("title") or "",
        rec.get("container") or "",
        rec.get("id") or "",
        " ".join(rec.get("collections") or []),
    ]).lower()
    return all(tok in hay for tok in query.lower().split())


def insert_citation_dialog(ctx, records):
    """Show the search/pick dialog.

    Returns a list of {'rec', 'locator', 'prefix', 'suffix'} or None.
    """
    records = sorted(records, key=lambda r: (
        (r.get("authors") or [{"family": "￿"}])[0]["family"].lower(),
        r.get("year") or 9999))
    collections = sorted(set(
        c for r in records for c in (r.get("collections") or [])))

    dialog, model = make_dialog(ctx, "Insert Citation — Mendeley", 300, 200)

    add_control(model, "FixedText", "lblSearch", 8, 8, 60, 10,
                Label="Search library:")
    if collections:
        add_control(model, "Edit", "search", 8, 20, 150, 13)
        add_control(model, "FixedText", "lblColl", 166, 8, 60, 10,
                    Label="Collection:")
        add_control(model, "ListBox", "collection", 166, 20, 126, 13,
                    Dropdown=True)
    else:
        add_control(model, "Edit", "search", 8, 20, 284, 13)
    add_control(model, "ListBox", "list", 8, 38, 284, 108,
                MultiSelection=True)
    add_control(model, "FixedText", "lblPages", 8, 152, 44, 10,
                Label="Page(s):")
    add_control(model, "Edit", "pages", 52, 150, 56, 12)
    add_control(model, "FixedText", "lblPrefix", 116, 152, 34, 10,
                Label="Prefix:")
    add_control(model, "Edit", "prefix", 148, 150, 56, 12)
    add_control(model, "FixedText", "lblSuffix", 210, 152, 30, 10,
                Label="Suffix:")
    add_control(model, "Edit", "suffix", 240, 150, 52, 12)
    add_control(model, "Button", "ok", 176, 178, 55, 15,
                Label="Insert", PushButtonType=_button_type("OK"),
                DefaultButton=True)
    add_control(model, "Button", "cancel", 237, 178, 55, 15,
                Label="Cancel", PushButtonType=_button_type("CANCEL"))

    toolkit = _smgr(ctx).createInstanceWithContext(
        "com.sun.star.awt.Toolkit", ctx)
    dialog.createPeer(toolkit, None)

    list_ctrl = dialog.getControl("list")
    search_ctrl = dialog.getControl("search")
    coll_ctrl = None
    if collections:
        coll_ctrl = dialog.getControl("collection")
        coll_ctrl.addItem("(All collections)", 0)
        for i, name in enumerate(collections):
            coll_ctrl.addItem(name, i + 1)
        coll_ctrl.selectItemPos(0, True)
    shown = []          # records currently in the listbox
    MAX_SHOWN = 300

    def refilter_safe():
        query = search_ctrl.getText().strip()
        wanted = None
        if coll_ctrl is not None:
            pos = coll_ctrl.getSelectedItemPos()
            if pos > 0:
                wanted = collections[pos - 1]
        del shown[:]
        for rec in records:
            if wanted is not None and \
                    wanted not in (rec.get("collections") or []):
                continue
            if not query or _matches(rec, query):
                shown.append(rec)
                if len(shown) >= MAX_SHOWN:
                    break
        lm = list_ctrl.getModel()
        try:
            lm.StringItemList = tuple(_record_label(r) for r in shown)
        except Exception:
            lm.setPropertyValue("StringItemList", uno.Any(
                "[]string", tuple(_record_label(r) for r in shown)))

    search_ctrl.addTextListener(_TextChange(refilter_safe))
    if coll_ctrl is not None:
        coll_ctrl.addItemListener(_ItemChange(refilter_safe))
    refilter_safe()

    result = dialog.execute()
    if result != 1:
        dialog.dispose()
        return None
    selected = list(list_ctrl.getSelectedItemsPos())
    locator = dialog.getControl("pages").getText().strip()
    prefix = dialog.getControl("prefix").getText().strip()
    suffix = dialog.getControl("suffix").getText().strip()
    dialog.dispose()
    items = []
    for pos in selected:
        if 0 <= pos < len(shown):
            items.append({"rec": shown[pos], "locator": locator,
                          "prefix": prefix, "suffix": suffix})
    return items or None


# ---------------------------------------------------------------- settings

API_HELP = """To use the Mendeley API you must register your own (free) \
API application:

1. Go to https://dev.mendeley.com — the Mendeley developer portal.
2. Sign in with your Mendeley / Elsevier account.
3. Open 'My Apps' and choose 'Register a new app'.
4. Enter any name and description. Set the redirect URL to:
        http://localhost:8123
5. Generate a client secret and save the app. Note the app ID (this \
is the client ID, a short number) and the secret, and enter both in \
this dialog. Copy the redirect URL you registered into the 'Redirect \
URI' field EXACTLY as you typed it there — Mendeley compares the two \
character by character, so even a trailing slash must match.
6. Click 'Sign in & sync' — your browser will open so you can \
authorize access to your library.

Note: Elsevier has at times closed new app registrations. If the \
portal will not let you register an app, use the BibTeX option \
instead: in Mendeley Reference Manager choose File > Export All > \
BibTeX and point this extension at the exported file.

Choosing OK opens dev.mendeley.com in your browser."""


def settings_dialog(ctx, frame, cfg, styles, sync_bibtex_fn, sync_api_fn,
                    open_url_fn=None):
    """Show settings; returns the updated cfg or None on cancel.

    sync_bibtex_fn(path) -> count      validates/parses a .bib file
    sync_api_fn(cfg, interactive) -> count   signs in and/or syncs
    open_url_fn(url)                   opens a URL in the browser
    """
    dialog, model = make_dialog(ctx, "Mendeley — Settings", 300, 232)

    add_control(model, "FixedText", "lblStyle", 8, 8, 80, 10,
                Label="Citation style:")
    add_control(model, "ListBox", "style", 8, 20, 284, 12, Dropdown=True)

    add_control(model, "FixedLine", "sep1", 8, 40, 284, 8,
                Label="Reference library source")
    add_control(model, "RadioButton", "srcBibtex", 8, 52, 284, 10,
                Label="BibTeX file exported from Mendeley Reference Manager")
    add_control(model, "Edit", "bibPath", 16, 65, 220, 12)
    add_control(model, "Button", "browse", 242, 65, 50, 12, Label="Browse...")

    add_control(model, "RadioButton", "srcApi", 8, 84, 284, 10,
                Label="Mendeley API (needs your own app credentials)")
    add_control(model, "FixedText", "lblCid", 16, 98, 60, 10,
                Label="Client ID:")
    add_control(model, "Edit", "clientId", 80, 96, 212, 12)
    add_control(model, "FixedText", "lblSec", 16, 113, 60, 10,
                Label="Client secret:")
    add_control(model, "Edit", "clientSecret", 80, 111, 212, 12,
                EchoChar=42)
    add_control(model, "FixedText", "lblRedir", 16, 128, 60, 10,
                Label="Redirect URI:")
    add_control(model, "Edit", "redirectUri", 80, 126, 212, 12,
                HelpText="Must match the redirect URL registered for "
                         "your app EXACTLY, including any trailing slash.")
    add_control(model, "Button", "signin", 16, 144, 84, 14,
                Label="Sign in && sync")
    add_control(model, "Button", "sync", 104, 144, 60, 14, Label="Sync now")
    add_control(model, "Button", "apihelp", 168, 144, 124, 14,
                Label="How to get credentials...")
    add_control(model, "FixedText", "status", 8, 164, 284, 22, Label="",
                MultiLine=True)

    add_control(model, "Button", "ok", 176, 210, 55, 15, Label="OK",
                PushButtonType=_button_type("OK"), DefaultButton=True)
    add_control(model, "Button", "cancel", 237, 210, 55, 15, Label="Cancel",
                PushButtonType=_button_type("CANCEL"))

    toolkit = _smgr(ctx).createInstanceWithContext(
        "com.sun.star.awt.Toolkit", ctx)
    dialog.createPeer(toolkit, None)

    style_ctrl = dialog.getControl("style")
    style_ids = [s.id for s in styles]
    for i, s in enumerate(styles):
        style_ctrl.addItem(s.name, i)
    try:
        style_ctrl.selectItemPos(style_ids.index(cfg.get("style", "apa")), True)
    except ValueError:
        style_ctrl.selectItemPos(0, True)

    dialog.getControl("srcBibtex").setState(cfg.get("source") != "api")
    dialog.getControl("srcApi").setState(cfg.get("source") == "api")
    dialog.getControl("bibPath").setText(cfg.get("bibtex_path", ""))
    dialog.getControl("clientId").setText(cfg.get("client_id", ""))
    dialog.getControl("clientSecret").setText(cfg.get("client_secret", ""))
    dialog.getControl("redirectUri").setText(
        cfg.get("redirect_uri", "http://localhost:8123/"))
    status = dialog.getControl("status")
    if not cfg.get("bibtex_path") and not cfg.get("client_id"):
        status.setText("Tip: in Mendeley Reference Manager use File > "
                       "Export All > BibTeX, then Browse to the exported "
                       "file above.")

    def current_cfg():
        new = dict(cfg)
        new["style"] = style_ids[max(0, style_ctrl.getSelectedItemPos())]
        new["source"] = "api" if dialog.getControl("srcApi").getState() \
            else "bibtex"
        new["bibtex_path"] = dialog.getControl("bibPath").getText().strip()
        new["client_id"] = dialog.getControl("clientId").getText().strip()
        new["client_secret"] = \
            dialog.getControl("clientSecret").getText().strip()
        new["redirect_uri"] = \
            dialog.getControl("redirectUri").getText().strip() \
            or "http://localhost:8123/"
        return new

    def browse():
        smgr = _smgr(ctx)
        picker = smgr.createInstanceWithContext(
            "com.sun.star.ui.dialogs.FilePicker", ctx)
        picker.appendFilter("BibTeX files (*.bib)", "*.bib")
        picker.appendFilter("All files (*.*)", "*.*")
        if picker.execute() == 1:
            url = picker.getSelectedFiles()[0]
            path = uno.fileUrlToSystemPath(url)
            dialog.getControl("bibPath").setText(path)
            dialog.getControl("srcBibtex").setState(True)
            dialog.getControl("srcApi").setState(False)
            try:
                count = sync_bibtex_fn(path)
                status.setText("Parsed %d references from the file." % count)
            except Exception as e:
                status.setText("Could not parse file: %s" % e)

    def do_sync(interactive):
        status.setText("Signing in via your browser..." if interactive
                       else "Syncing from the Mendeley API...")
        try:
            count = sync_api_fn(current_cfg(), interactive)
            status.setText("Synced %d references from Mendeley." % count)
            dialog.getControl("srcApi").setState(True)
            dialog.getControl("srcBibtex").setState(False)
        except Exception as e:
            status.setText("Sync failed: %s" % e)
            message_box(ctx, frame, "Sync failed:\n\n%s" % e,
                        "Mendeley — sync error", "ERRORBOX")

    # Radio buttons are not auto-grouped in runtime dialogs; keep them
    # mutually exclusive by hand.
    src_bib = dialog.getControl("srcBibtex")
    src_api = dialog.getControl("srcApi")
    src_bib.addItemListener(_ItemChange(
        lambda: src_api.setState(not src_bib.getState())))
    src_api.addItemListener(_ItemChange(
        lambda: src_bib.setState(not src_api.getState())))

    def api_help():
        message_box(ctx, frame, API_HELP, "Mendeley API credentials")
        if open_url_fn:
            open_url_fn("https://dev.mendeley.com")

    dialog.getControl("browse").addActionListener(_Action(browse))
    dialog.getControl("signin").addActionListener(
        _Action(lambda: do_sync(True)))
    dialog.getControl("sync").addActionListener(
        _Action(lambda: do_sync(False)))
    dialog.getControl("apihelp").addActionListener(_Action(api_help))

    result = dialog.execute()
    new_cfg = current_cfg() if result == 1 else None
    dialog.dispose()
    return new_cfg
