"""OrcaSlicer plugin: prices every build plate of the open project."""

import orca

from . import _assets, host

VERSION = '0.6.2'

HOST = host.Host(VERSION)
PERMISSIONS = host.permissions()  # at import: no audit scope is open yet (docs/spike.md §1)


class CalculatorPage(orca.pages.PagesPluginCapabilityBase):
    def get_name(self):
        return "Print Calculator"

    def get_type(self):
        return getattr(getattr(orca, "PluginType", None), "Pages", None)

    def get_icon(self):
        try:
            return HOST.icon_path(_assets.ICON_PNG)
        except Exception:
            host.log.exception("get_icon failed")
            return ""

    def get_ui(self):
        return _assets.APP_HTML

    def on_load(self):
        # Storage is not asked for here: an Orca Cloud install started offline has none until networking is up
        # ("Cloud plugin storage is unavailable before networking is initialized"). It is asked for on first use.
        HOST.page = self
        host.log.info("loaded %s", VERSION)

    def on_unload(self):
        if HOST.page is self:
            HOST.page = None

    def on_message(self, data):
        HOST.on_message(self, data)

    def on_lifecycle_event(self, event, ctx):
        try:
            HOST.on_event(self, event, ctx)
        except Exception:
            host.log.exception("lifecycle event %s failed", host.event_name(event))


@orca.plugin
class PrintCalculator(orca.base):
    def register_capabilities(self):
        request = getattr(orca, "request_permissions", None)
        if request is not None:
            try:
                request(**PERMISSIONS)
            except Exception:
                host.log.exception("request_permissions failed")
        orca.register_capability(CalculatorPage)
