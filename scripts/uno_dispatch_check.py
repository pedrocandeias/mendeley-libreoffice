#!/usr/bin/env python3
"""Verify that org.mendeley.lo:* URLs resolve to our protocol handler."""

import sys
import time

import uno
from com.sun.star.util import URL as UnoURL


def connect(port, attempts=30):
    local = uno.getComponentContext()
    resolver = local.ServiceManager.createInstanceWithContext(
        "com.sun.star.bridge.UnoUrlResolver", local)
    url = ("uno:socket,host=localhost,port=%d;urp;"
           "StarOffice.ComponentContext" % port)
    for _ in range(attempts):
        try:
            return resolver.resolve(url)
        except Exception:
            time.sleep(1)
    raise SystemExit("could not connect to soffice")


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 2002
    ctx = connect(port)
    smgr = ctx.ServiceManager
    desktop = smgr.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
    doc = desktop.loadComponentFromURL("private:factory/swriter",
                                       "_blank", 0, ())
    frame = doc.getCurrentController().getFrame()
    transformer = smgr.createInstanceWithContext(
        "com.sun.star.util.URLTransformer", ctx)

    ok = True
    for cmd in ("InsertCitation", "InsertBibliography", "Refresh",
                "Settings", "About"):
        url = UnoURL()
        url.Complete = "org.mendeley.lo:" + cmd
        _, url = transformer.parseStrict(url)
        dispatch = frame.queryDispatch(url, "", 0)
        found = dispatch is not None
        ok &= found
        print(("PASS  " if found else "FAIL  ") + cmd)
    doc.close(False)
    print("DISPATCH " + ("OK" if ok else "FAILED"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
