#!/usr/bin/env python3
"""CLI sign-in/sync for debugging — uses the same code paths as the
extension. Point XDG_CONFIG_HOME at the snap's config dir so tokens and
the library cache land where LibreOffice reads them:

    XDG_CONFIG_HOME=~/snap/libreoffice/current/.config \
        python3 scripts/api_signin.py
"""

import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..",
                                "src", "python", "pythonpath"))

from mlo import config  # noqa: E402


def open_browser(url):
    print("Opening browser:\n  %s" % url)
    try:
        subprocess.Popen(["xdg-open", url],
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    except OSError:
        print("Could not launch a browser — open the URL above manually.")


def main():
    cfg = config.load_config()
    print("config dir:", config.config_dir())
    print("client_id=%r redirect_uri=%r" % (cfg.get("client_id"),
                                            cfg.get("redirect_uri")))
    records = config.sync_api_library(cfg, interactive=True,
                                      open_browser=open_browser)
    print("SYNC OK — %d references cached." % len(records))
    for r in records[:5]:
        print("  -", (r.get("title") or "(untitled)")[:70])


if __name__ == "__main__":
    main()
