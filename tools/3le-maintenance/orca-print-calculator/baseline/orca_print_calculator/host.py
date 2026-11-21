"""Host side: page RPC, slice capture, lifecycle and stale logic. Everything that calls `orca` lives here.

Threads (docs/spike.md): `on_message` and every lifecycle event except `GCodeExportFinished` arrive on the
UI thread. `GCodeExportFinished` arrives on the slicing worker, where only `core.split_export_msg` and the
stash lock are used: no `orca` call, no file I/O. Spoolman requests run on a plugin thread.
Payload field names follow ui/src/state/types.ts; unknown values are None, never 0.
"""

import base64
import binascii
import json
import logging
import logging.handlers
import os
import re
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import orca

from . import core

log = logging.getLogger("orca_print_calculator")
log.propagate = False

LOG_FILE = "plugin.log"
LOG_CAP = 512 * 1024
# A new name, not orca_print_calculator.png: OrcaSlicer drops the extension and tries .svg first, so the
# orca_print_calculator.svg older versions wrote would win.
ICON_FILE = "orca_print_calculator-icon.png"
IMPORT_CAP = 100 * 1024 * 1024  # ui/src/components/plates/importFlow.ts MAX_BYTES
B64_CAP = (IMPORT_CAP + 2) // 3 * 4
IMPORT_CODES = {"bad_zip": "not_zip"}  # core code -> code importFlow.ts maps

# PlateCreated: Orca has no plate move/reorder event; a new plate may shift indexes, so flag everything.
STALE_EVENTS = ("ObjectAdded", "ObjectDeleted", "ObjectTransformed", "ObjectChanged", "PresetSelected", "PresetSaved",
                "PlateCreated")
CLEAR_EVENTS = ("NewProject", "ProjectOpened", "ProjectClosed")
HOST_EVENTS = ("PresetSelected", "ProjectOpened", "NewProject", "ProjectClosed")
STASH_CAP = 8          # exports waiting for a SlicingJobComplete; a user "Export G-code" may never get one
STASH_MAX_AGE = 120    # seconds; an older export is not this job's
EVENTS = STALE_EVENTS + CLEAR_EVENTS + ("GCodeExportFinished", "SlicingJobComplete", "PlateDeleted")
_MISSING = object()
_ASYNC = object()  # handler answers later from its own thread

opener = None  # None = core.open_url (same-origin redirects only); replaced in tests
clock = time.monotonic  # replaced in tests


class BadArgs(Exception):
    pass


def temp_read_root():
    """Orca's temp model tree (spike §1). macOS verified from source and on disk; Linux and Windows UNVERIFIED:
    wx GetTempDir() and tempfile.gettempdir() share TMPDIR/TEMP/TMP but their fallbacks differ."""
    base = tempfile.gettempdir()
    if os.name != "nt":
        base = os.path.join(base, "orcaslicer_%d" % os.getuid())  # Windows: per_user_temp_id() is ""
    return os.path.join(base, "orcaslicer_model", "*")


def permissions():
    return {"threading": True, "fs_read": [temp_read_root()]}


TEMP_MODEL_DIR = os.path.dirname(temp_read_root())  # replaced in tests


def _in_temp_tree(path):
    """Only Orca's own temp G-code is read: a user export elsewhere is outside the fs grant and would prompt."""
    try:
        root = os.path.realpath(TEMP_MODEL_DIR)
        return os.path.commonpath([root, os.path.realpath(path)]) == root
    except (OSError, ValueError):  # ValueError: different drives on Windows
        return False


# ------------------------------------------------------------------ small helpers

def _try(fn):
    try:
        return fn()
    except Exception as exc:
        log.info("host call failed: %s: %s", type(exc).__name__, exc)
        return None


def _text(value):
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    if not isinstance(value, str):
        return None
    return value.strip().strip('"').strip() or None


def _at(items, i):
    return items[i] if items and 0 <= i < len(items) else None


def _price(value):
    """Cost per kg: positive number or None. Orca's default `filament_cost` 0 means "not set"."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if value > 0 and value != float("inf") else None


def _hex(value):
    return value.upper() if isinstance(value, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", value) else None


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _code(ctx):
    code = getattr(ctx, "code", None)
    return getattr(code, "name", None) or str(code)


def event_name(event):
    events = getattr(orca, "LifecycleEvent", None)
    for name in EVENTS:
        if event == getattr(events, name, _MISSING):
            return name
    return None


def slots_from(fields, slots, presets=()):
    """HostSlot rows: per-slot fields from G-code/3mf config, gaps filled from the live presets."""
    rows = []
    for n, grams, color in slots:
        i = n - 1
        p = _at(presets, i) or {}
        rows.append({
            "n": n,
            "preset": _at(fields.get("filament_presets"), i) or p.get("preset") or "",
            "grams": grams,
            "color": color or _hex(_at(fields.get("filament_colour"), i)) or p.get("color"),
            "costPerKg": _price(_at(fields.get("filament_cost"), i)) or p.get("costPerKg"),
            "notes": _at(fields.get("filament_notes"), i) or p.get("notes") or "",
            "material": _at(fields.get("filament_type"), i) or p.get("material"),
        })
    return rows


def plate(index, seconds, slots, source, file_name=None, consumption=None):
    """`consumption`: "known" (a slot reported a weight), "zero" (the file states 0 g) or "missing" (no usable weight
    data: the UI must not price it as free filament). Left unset it follows `slots`."""
    return {"index": index, "name": None, "seconds": seconds, "stale": False, "thumb": None,
            "slicedAt": _now() if source == "slice" else None, "source": source, "fileName": file_name,
            "slots": slots, "consumption": consumption or ("known" if slots else "missing")}


def spoolman_data(raw):
    """core.spoolman_fetch rows -> SpoolmanData (camelCase, match.ts)."""
    return {
        "currency": raw["currency"],
        "filaments": [{"id": f["id"], "name": f["name"] or "", "vendor": f["vendor"], "material": f["material"],
                       "price": f["price"], "weight": f["weight"],
                       "colorHex": "#" + f["color_hex"].upper() if f["color_hex"] else None,
                       "orcaPreset": f.get("orca_preset")} for f in raw["filaments"]],
        "spools": [{"id": s["id"], "filamentId": s["filament_id"], "price": s["price"],
                    "initialWeight": s["initial_weight"], "remainingWeight": s["remaining_weight"],
                    "archived": s["archived"], "lastUsed": s["last_used"], "orcaPreset": s.get("orca_preset")}
                   for s in raw["spools"]],
    }


def _setup_log(folder):
    if log.handlers:
        return
    try:
        handler = logging.handlers.RotatingFileHandler(os.path.join(folder, LOG_FILE), maxBytes=LOG_CAP,
                                                       backupCount=1, encoding="utf-8")
    except OSError:
        return
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(threadName)s] %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)


# ------------------------------------------------------------------ host state

class Host:
    def __init__(self, version):
        self.version = version
        self.page = None
        self.storage_dir = None
        self.lock = threading.Lock()
        self.stash = []          # [(path, failed, time)] from GCodeExportFinished, last STASH_CAP; guarded by lock
        self.denied = set()      # Spoolman bases a worker was denied: next fetch probes on the UI thread first
        self.inflight = {}       # Spoolman base -> request ids waiting on the one running fetch; guarded by lock
        self.plates = {}         # plate index -> HostPlate; UI thread only
        self.path_index = {}     # temp G-code path -> plate index (Orca keeps one path per plate); UI thread only
        self.unreadable = set()  # store files that could neither be read nor set aside: never overwritten
        self.unloaded = set()    # store files not read because storage was unavailable: never overwritten until read
        self.storage_warned = False

    # -- UI thread
    def storage(self):
        """The plugin's storage folder, or "" while OrcaSlicer can't give one yet (an Orca Cloud install started
        offline: "Cloud plugin storage is unavailable before networking is initialized"). Never raises; asked
        again on every use until it answers, and the plugin runs on built-in defaults meanwhile."""
        if self.storage_dir is None:
            try:
                folder = orca.host.plugin.storage()
            except Exception as exc:
                if not self.storage_warned:   # once: it is asked again on every use
                    self.storage_warned = True
                    log.warning("storage not available yet: %s", exc)
                return ""
            if not folder:
                return ""
            self.storage_dir = folder
            _setup_log(folder)
        return self.storage_dir

    def storage_or_raise(self):
        folder = self.storage()
        if not folder:
            raise core.CoreError("io", "plugin storage not available yet")
        return folder

    def post(self, msg):
        page = self.page
        if page is None:
            return
        try:
            page.post_message(msg)
        except Exception:
            log.exception("post_message failed")

    def event(self, name, data):
        self.post({"type": "event", "name": name, "data": data})

    def icon_path(self, png_b64):
        if not self.storage():   # the copy shipped in the package (OrcaSlicer may ask for the icon only at load)
            shipped = os.path.join(os.path.dirname(os.path.abspath(__file__)), ICON_FILE)
            return shipped if os.path.isfile(shipped) else ""
        path = os.path.join(self.storage(), ICON_FILE)
        try:
            png = base64.b64decode(png_b64)
            if not os.path.isfile(path) or Path(path).read_bytes() != png:
                core._atomic_write(path, png)
        except (OSError, ValueError, core.CoreError) as exc:
            log.warning("icon not written: %s", exc)
            return ""
        return path

    def host_info(self):
        bundle = _try(orca.host.preset_bundle)
        printer = _try(bundle.current_printer_preset) if bundle else None
        cfg = (lambda k: _text(_try(lambda: printer.config_value(k)))) if printer else (lambda k: None)
        model = cfg("printer_model") or (_text(_try(lambda: bundle.full_config_value("printer_model"))) if bundle else None)
        path = _text(_try(lambda: orca.host.plater().project_path()))
        name = re.sub(r"\.3mf$", "", os.path.basename(path), flags=re.I) if path else None
        preset = _text(_try(lambda: printer.name)) if printer else None  # slot spool picks are kept per printer preset
        return {"projectName": name or None, "printerModel": model, "printerVendor": cfg("printer_vendor"), "printerPreset": preset,
                "pluginVersion": self.version, "appLanguage": _text(_try(lambda: orca.host.app_language()))}

    def preset_slots(self):
        bundle = _try(orca.host.preset_bundle)
        presets = (_try(bundle.current_filament_presets) if bundle else None) or []
        colours = _text(_try(lambda: bundle.full_config_value("filament_colour"))) if bundle else None
        colours = colours.split(";") if colours else []
        rows = []
        for i, p in enumerate(presets):
            cfg = (lambda k, p=p: _text(_try(lambda: p.config_value(k)))) if p is not None else (lambda k: None)
            rows.append({"preset": getattr(p, "name", None) or "", "costPerKg": _price(cfg("filament_cost")),
                         "notes": cfg("filament_notes") or "", "material": cfg("filament_type"),
                         "color": _hex(_at(colours, i))})
        return rows

    def plate_list(self):
        return [self.plates[i] for i in sorted(self.plates)]

    def push_plates(self, **extra):
        self.event("plates", {"plates": self.plate_list(), **extra})

    def spooler(self):
        folder = self.storage()
        datadir = next((p.parent for p in Path(folder).parents if p.name == "orca_plugins"), None) if folder else None
        info = core.read_spooler_files(datadir) if datadir else {"detected": False}
        return {"url": info["spoolman_url"], "presetToFilament": info["preset_to_filament"],
                "presetToSpool": info["preset_to_spool"]} if info["detected"] else None

    def load(self, name, kind):
        """Parsed file or None. Wrong JSON type is set aside like a corrupt file. A file that can be neither
        read nor set aside degrades to None (the rest of the state still loads) and is locked against saves."""
        if not self.storage():   # built-in defaults until storage is available; the file is not saved over meanwhile
            self.unloaded.add(name)
            return None
        path = os.path.join(self.storage(), name)
        try:
            data = core.load_json(path, None)
            if data is not None and not isinstance(data, kind):
                core._set_aside(Path(path))
                data = None
        except core.CoreError as exc:
            log.warning("%s unreadable (%s): loading without it, saves refused", name, exc.code)
            self.unreadable.add(name)
            return None
        self.unreadable.discard(name)
        self.unloaded.discard(name)
        return data

    def save(self, name, obj):
        if name in self.unreadable or name in self.unloaded:   # unloaded: the page holds defaults, not the file
            raise core.CoreError("unreadable", name)
        core.save_json(os.path.join(self.storage_or_raise(), name), obj)

    def state(self):
        settings, quotes = self.load(core.SETTINGS_FILE, dict), self.load(core.QUOTES_FILE, list)
        unreadable = [key for key, name in (("settings", core.SETTINGS_FILE), ("quotes", core.QUOTES_FILE))
                      if name in self.unreadable or name in self.unloaded]  # null + listed here = "can't read", not "first run"
        unloaded = [key for key, name in (("settings", core.SETTINGS_FILE), ("quotes", core.QUOTES_FILE))
                    if name in self.unloaded]  # no storage folder yet: the page reads them again before saving
        return {"host": self.host_info(), "plates": self.plate_list(), "settings": settings, "quotes": quotes,
                "spooler": self.spooler(), "unreadable": unreadable, "unloaded": unloaded}

    def on_message(self, page, data):
        self.page = page
        self.storage()   # first use: opens the log file once OrcaSlicer has a storage folder; never raises
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except ValueError:
                return
        if not isinstance(data, dict):
            return
        if data.get("type") != "cmd":  # "ready" only binds the page: the page loads through get_state
            return
        rid, cmd, args = data.get("id"), data.get("cmd"), data.get("args")
        handler = COMMANDS.get(cmd) if isinstance(cmd, str) else None
        try:
            if handler is None:
                raise core.CoreError("unknown_command")
            if not isinstance(args, dict):
                raise BadArgs()
            result = handler(self, args, rid)
            if result is not _ASYNC:
                self.post({"type": "res", "id": rid, "ok": True, "data": result})
        except BadArgs:
            self.reply_error(rid, "bad_args")
        except core.CoreError as exc:
            log.info("cmd %s failed: %s", cmd, exc.code)
            self.reply_error(rid, exc.code)
        except Exception:
            log.exception("cmd %s raised", cmd)
            self.reply_error(rid, "host_error")

    def reply_error(self, rid, code):
        self.post({"type": "res", "id": rid, "ok": False, "error": code})

    def on_event(self, page, event, ctx):
        self.page = page
        name = event_name(event)
        if name == "GCodeExportFinished":
            self.stash_export(ctx)  # slicing worker: nothing else
            return
        if name is None:
            return
        _try(self.storage)  # log file; a failure here must not block capture
        if name == "SlicingJobComplete":
            self.capture(ctx)
        elif name == "PlateDeleted":
            self.plate_deleted(getattr(ctx, "index", -1))
        elif name in CLEAR_EVENTS:
            self.clear()
        elif name in STALE_EVENTS:
            if name == "PlateCreated":
                self.path_index = {}  # a plate inserted before others may renumber them: re-learn from scratch
            self.mark_stale()
        if name in HOST_EVENTS:
            self.event("host", {"kind": name, "host": self.host_info()})

    # -- slicing worker
    def stash_export(self, ctx):
        """Slicing worker: no orca call, no logging (the log file is written on the UI thread only)."""
        path, error = core.split_export_msg(getattr(ctx, "msg", ""))
        failed = bool(error) or _code(ctx) != "Ok" or not path
        with self.lock:
            self.stash = (self.stash + [(path, failed, clock())])[-STASH_CAP:]

    # -- UI thread: capture and plate bookkeeping
    def pick_export(self, ctx):
        """The temp G-code path this job wrote, or None (logged)."""
        with self.lock:
            stash, self.stash = self.stash, []
        code, now = _code(ctx), clock()
        fresh = [e for e in stash if now - e[2] <= STASH_MAX_AGE]
        if len(fresh) < len(stash):
            log.info("%d stale export(s) dropped", len(stash) - len(fresh))
        if code != "Ok":
            log.info("slicing job %s (%s): %d export(s) dropped", code, getattr(ctx, "msg", ""), len(fresh))
            return None
        if not fresh:
            log.info("slicing job complete with no export stashed")
            return None
        if len(fresh) > 1:
            log.warning("slicing job complete with %d exports stashed; pairing the last", len(fresh))
        path, failed, _ = fresh[-1]
        if failed:
            log.warning("G-code export failed; plate not updated")
            return None
        if not _in_temp_tree(path):
            log.info("export outside Orca's temp tree (user export?); not read")
            return None
        return path

    def plate_for(self, path):
        """Known path -> its plate (stays right if the user switched plates mid-slice); else the current plate."""
        current = _try(lambda: orca.host.model().current_plate_index())
        current = current if isinstance(current, int) and not isinstance(current, bool) and current >= 0 else None
        known = self.path_index.get(path)
        if known is not None and current is not None and known != current:
            log.info("plate %d's G-code finished while plate %d is selected; using %d", known, current, known)
        index = known if known is not None else current
        if index is not None:
            self.path_index = {**{p: i for p, i in self.path_index.items() if i != index}, path: index}
        return index

    def capture(self, ctx):
        path = self.pick_export(ctx)
        if path is None:
            return
        index = self.plate_for(path)
        if index is None:
            log.warning("no current plate index; plate not updated")
            return
        try:
            head, tail = core.read_gcode_parts(path)
        except core.CoreError as exc:
            log.warning("G-code read failed: %s", exc.code)
            return
        parsed = core.parse_gcode(head, tail)
        slots = slots_from(parsed, [(s["n"], s["grams"], None) for s in parsed["slots"]], self.preset_slots())
        self.plates = {**self.plates, index: plate(index, parsed["seconds"], slots, "slice", consumption=parsed["consumption"])}
        log.info("plate %d captured: seconds=%s slots=%d", index, parsed["seconds"], len(slots))
        self.push_plates()

    def mark_stale(self):
        if all(p["stale"] for p in self.plates.values()):
            return
        self.plates = {i: {**p, "stale": True} for i, p in self.plates.items()}
        self.push_plates()

    def plate_deleted(self, index):
        if not isinstance(index, int) or index < 0:
            self.mark_stale()  # which plate is unknown: keep the data, flag all of it
            return
        shift = lambda i: i - 1 if i > index else i  # noqa: E731
        self.plates = {shift(i): {**p, "index": shift(i)} for i, p in self.plates.items() if i != index}
        self.path_index = {p: shift(i) for p, i in self.path_index.items() if i != index}
        self.push_plates(deleted=index)  # lets the page shift its per-plate controls the same way

    def clear(self):
        with self.lock:
            self.stash = []
        had = bool(self.plates)
        self.plates = {}
        self.path_index = {}
        if had:
            self.push_plates()


# ------------------------------------------------------------------ commands

def _arg(args, key, kind):
    value = args.get(key)
    if not isinstance(value, kind) or isinstance(value, bool):
        raise BadArgs()
    return value


def cmd_get_state(host, args, rid):
    return host.state()


def cmd_check_requirements(host, args, rid):
    """Settings › Requirements › Check again: re-read Spooler's files."""
    return {"spooler": host.spooler()}


def cmd_save_settings(host, args, rid):
    host.save(core.SETTINGS_FILE, _arg(args, "settings", dict))
    return {}


def cmd_save_quotes(host, args, rid):
    host.save(core.QUOTES_FILE, _arg(args, "quotes", list))
    return {}


def cmd_spoolman_fetch(host, args, rid):
    """One fetch per base on a worker; later requests for the same base join it. After a worker was
    denied, a single bounded /api/v1/info probe runs here on the UI thread so Orca can show its prompt."""
    url = _arg(args, "url", str)
    try:
        base = core.normalize_base_url(url)
    except ValueError as exc:
        raise core.CoreError("bad_url", str(exc)) from exc
    with host.lock:
        probe = base in host.denied
    if probe:
        core.spoolman_probe(base, opener=opener)  # raises: the reply carries the code, base stays on the probe path
        with host.lock:
            host.denied.discard(base)
    with host.lock:
        if base in host.inflight:
            host.inflight[base].append(rid)
            return _ASYNC
        host.inflight[base] = [rid]

    def finish(reply):
        with host.lock:
            waiting = host.inflight.pop(base, [])
        for wid in waiting:
            host.post({"type": "res", "id": wid, **reply})

    def run():
        reply = {"ok": False, "error": "host_error"}
        try:
            reply = {"ok": True, "data": spoolman_data(core.spoolman_fetch(base, opener=opener))}
        except core.CoreError as exc:
            log.info("spoolman_fetch failed: %s", exc.code)  # code only: the detail can name the host
            if exc.code == "denied":
                with host.lock:
                    host.denied.add(base)
            reply = {"ok": False, "error": exc.code}
        except Exception as exc:
            log.error("spoolman_fetch raised %s", type(exc).__name__)
        finally:
            finish(reply)  # every exit path frees the base and answers every waiting id

    try:
        threading.Thread(target=run, name="opc-spoolman", daemon=True).start()
    except Exception as exc:  # threading denied or exhausted: nobody may stay joined to a dead fetch
        log.error("spoolman_fetch: thread not started (%s)", type(exc).__name__)
        finish({"ok": False, "error": "host_error"})
    return _ASYNC


def cmd_import_sliced(host, args, rid):
    name, b64 = _arg(args, "name", str), _arg(args, "b64", str)
    if len(b64) > B64_CAP:
        raise core.CoreError("too_big")
    try:
        data = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise core.CoreError("bad_b64") from exc
    try:
        infos, fields = core.read_sliced_3mf(data)
    except core.CoreError as exc:
        raise core.CoreError(IMPORT_CODES.get(exc.code, exc.code), exc.detail) from exc
    if not infos:
        raise core.CoreError("no_slice_info")
    plates = []
    for info in infos:
        used = [((f["id"] if f["id"] is not None else pos), f["used_g"], f["color"], f["type"])
                for pos, f in enumerate(info["filaments"], start=1)]
        slots = slots_from(fields, [(n, g, c) for n, g, c, _ in used])
        for row, (_, _, _, kind) in zip(slots, used):
            row["material"] = kind or row["material"]
        plates.append(plate(info["index"], info["prediction"], slots, "file", name))
    log.info("imported %d plate(s)", len(plates))
    return {"plates": plates}


def cmd_export_file(host, args, rid):
    name, text = _arg(args, "name", str), _arg(args, "text", str)
    try:
        return {"path": core.write_export(host.storage_or_raise(), name, text)}
    except ValueError as exc:
        raise core.CoreError("bad_name", str(exc)) from exc


COMMANDS = {
    "get_state": cmd_get_state,
    "check_requirements": cmd_check_requirements,
    "save_settings": cmd_save_settings,
    "save_quotes": cmd_save_quotes,
    "spoolman_fetch": cmd_spoolman_fetch,
    "import_sliced": cmd_import_sliced,
    "export_file": cmd_export_file,
}
