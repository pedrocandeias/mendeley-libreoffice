"""UNO component: protocol handler for org.mendeley.lo:* menu commands."""

import unohelper

from com.sun.star.frame import XDispatch, XDispatchProvider
from com.sun.star.lang import XInitialization, XServiceInfo

IMPLEMENTATION_NAME = "org.mendeley.libreoffice.ProtocolHandler"
PROTOCOL = "org.mendeley.lo:"


class MendeleyProtocolHandler(unohelper.Base, XServiceInfo,
                              XDispatchProvider, XDispatch,
                              XInitialization):
    def __init__(self, ctx, *args):
        self.ctx = ctx
        self.frame = None

    # XInitialization — the frame this handler serves is passed here.
    def initialize(self, args):
        if args:
            self.frame = args[0]

    # XDispatchProvider
    def queryDispatch(self, url, target_frame_name, search_flags):
        if url.Protocol == PROTOCOL:
            return self
        return None

    def queryDispatches(self, requests):
        return [self.queryDispatch(r.FeatureURL, r.FrameName, r.SearchFlags)
                for r in requests]

    # XDispatch
    def dispatch(self, url, arguments):
        if url.Protocol != PROTOCOL:
            return
        from mlo import actions
        actions.dispatch(self.ctx, self.frame, url.Path)

    def addStatusListener(self, listener, url):
        pass

    def removeStatusListener(self, listener, url):
        pass

    # XServiceInfo
    def getImplementationName(self):
        return IMPLEMENTATION_NAME

    def supportsService(self, name):
        return name == "com.sun.star.frame.ProtocolHandler"

    def getSupportedServiceNames(self):
        return ("com.sun.star.frame.ProtocolHandler",)


g_ImplementationHelper = unohelper.ImplementationHelper()
g_ImplementationHelper.addImplementation(
    MendeleyProtocolHandler,
    IMPLEMENTATION_NAME,
    ("com.sun.star.frame.ProtocolHandler",),
)
