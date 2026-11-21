"""Orca-free logic: G-code and slice-info parsing, Spoolman client, storage.

Standard library only. Nothing here imports `orca`, so it runs under plain unittest.
Layout facts come from docs/spike.md.
"""
import copy
import io
import json
import math
import os
import re
import socket
import struct
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
import zlib
import http.client
from pathlib import Path

HEAD_BYTES = 4096
HEAD_CAP = 512 * 1024
TAIL_BYTES = 192 * 1024
SLICE_INFO_CAP = 5 * 1024 * 1024
SPOOLMAN_MAX_BYTES = 20 * 1024 * 1024
JSON_FILE_CAP = 5 * 1024 * 1024
# settings.json / quotes.json: a file the plugin wrote must never look oversized to the plugin.
STORE_SAVE_CAP = 16 * 1024 * 1024
STORE_LOAD_CAP = 2 * STORE_SAVE_CAP
SPOOLMAN_TIMEOUT = 5     # per socket operation
SPOOLMAN_DEADLINE = 15   # whole fetch (all requests and reads); worst case deadline + one timeout
PROBE_TIMEOUT = 2        # UI-thread probe that lets Orca show its network prompt
PROBE_DEADLINE = 3
ZIP_ENTRY_CAP = 10000    # a sliced 3mf holds tens of entries
ZIP_CD_CAP = 4 * 1024 * 1024
clock = time.monotonic   # replaced in tests
EXPORT_CAP = 10 * 1024 * 1024
EXPORT_NAME_MAX = 80

SETTINGS_FILE = "settings.json"
QUOTES_FILE = "quotes.json"
EXPORT_DIR = "exports"
EXPORT_EXTENSIONS = (".html", ".csv")

_DENY_COMPONENTS = frozenset({"conf", "config", "secret", "secrets", "cert", "certs"})
_DENY_SUFFIXES = (".conf", ".ini")


class CoreError(Exception):
    """Failure with a stable machine-readable `code` and a human `detail`."""

    def __init__(self, code, detail=""):
        super().__init__("%s: %s" % (code, detail) if detail else code)
        self.code = code
        self.detail = detail


# ---------------------------------------------------------------- G-code (T3.1)

def split_export_msg(msg):
    """`GCodeExportFinished` msg is `path` or `path\\n<error>` -> (path, error | None)."""
    text = msg if isinstance(msg, str) else ""
    path, _, error = text.partition("\n")
    error = error.strip()
    return path.strip(), (error or None)


def _decode(raw):
    return raw.decode("utf-8", errors="replace")


def _read_head(fh, size):
    """First 4 KB, extended to CONFIG_BLOCK_END when the config block sits at the head (Bambu)."""
    data = fh.read(HEAD_BYTES)
    while len(data) < HEAD_CAP:
        text = _decode(data)
        if "CONFIG_BLOCK_END" in text or "EXECUTABLE_BLOCK_START" in text:
            break
        if "HEADER_BLOCK_END" in text and "CONFIG_BLOCK_START" not in text:
            break  # Orca layout: config is at the end of the file, not here
        more = fh.read(64 * 1024)
        if not more:
            break
        data += more
    cut = _decode(data[:HEAD_CAP])
    end = cut.find("CONFIG_BLOCK_END")
    if end != -1:
        nl = cut.find("\n", end)
        cut = cut[: nl if nl != -1 else len(cut)]
    return cut


def read_gcode_parts(path):
    """(head, tail) text of a G-code file; short files and bad bytes are fine."""
    try:
        with open(path, "rb") as fh:
            size = os.fstat(fh.fileno()).st_size
            head = _read_head(fh, size)
            fh.seek(max(0, size - TAIL_BYTES))
            tail = _decode(fh.read(TAIL_BYTES))
    except PermissionError as exc:
        raise CoreError("denied", str(exc)) from exc
    except FileNotFoundError as exc:
        raise CoreError("missing", str(exc)) from exc
    except OSError as exc:
        raise CoreError("io", str(exc)) from exc
    return head, tail


def parse_duration(text):
    """`1d 2h 3m 4s`, `2h 3m`, `45s` -> seconds (int) or None."""
    if not isinstance(text, str) or not re.fullmatch(r"\s*(?:\d+\s*[dhms]\s*)+", text):
        return None
    scale = {"d": 86400, "h": 3600, "m": 60, "s": 1}
    return sum(int(n) * scale[u] for n, u in re.findall(r"(\d+)\s*([dhms])", text))


def _first(pattern, *texts):
    for text in texts:
        found = re.search(pattern, text, re.M)
        if found:
            return found
    return None


def _floats(raw):
    """Comma list -> floats; blank or bad entries -> None. Orca's numeric vectors use commas."""
    if raw is None:
        return None
    out = []
    for item in raw.split(","):
        try:
            value = float(item)
        except ValueError:
            value = None
        out.append(value if value is not None and math.isfinite(value) else None)
    return out


def _split_strings(raw):
    """`;`-separated slot strings. Quoted entries may hold `;` and use C-style escapes."""
    if raw is None:
        return None
    out, cur, quoted, esc = [], [], False, False
    for ch in raw:
        if esc:
            cur.append("\n" if ch == "n" else ch)
            esc = False
        elif quoted and ch == "\\":
            esc = True
        elif ch == '"':
            quoted = not quoted
        elif ch == ";" and not quoted:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur))
    return out


def _config(*texts):
    """`; key = value` lines; later texts win. Header lines use `key:` so they are not caught."""
    wanted = ("printer_model", "filament_settings_id", "filament_cost", "filament_density",
              "filament_notes", "filament_colour", "filament_type")
    found = {}
    for text in texts:
        for key, value in re.findall(r"^; (\w+) = (.*)$", text, re.M):
            if key in wanted:
                found[key] = value.rstrip("\r")
    return found


def _slots(tail, head):
    series = {}
    for unit in ("mm", "cm3", "g"):
        found = _first(r"^; filament used \[%s\] = (.*)$" % re.escape(unit), tail, head)
        series[unit] = _floats(found.group(1)) if found else None
    count = max((len(v) for v in series.values() if v), default=0)
    slots = []
    for i in range(count):
        row = {u: (series[u][i] if series[u] and i < len(series[u]) else None) for u in series}
        if any(v and v > 0 for v in row.values()):
            grams = row["g"] if row["g"] is None or row["g"] >= 0 else None  # negative: unreadable, never a credit
            slots.append({"n": i + 1, "grams": grams, "mm": row["mm"], "cm3": row["cm3"]})
    return slots, series["g"]


def _times(head, tail):
    """Print duration in seconds plus flavour.

    Bambu: `; model printing time: A; total estimated time: B`. B is used as `seconds`: it matches
    slice_info `prediction` and what Orca's slice panel shows, and it is the time the machine is
    occupied (A leaves out prepare and filament changes). A is exposed as `model_seconds`.
    Orca: `; estimated printing time (normal mode) = X`.
    """
    bbl = _first(r"^; model printing time: ([^;\n]*); total estimated time: ([^;\n]*)", head, tail)
    if bbl:
        return parse_duration(bbl.group(2)), parse_duration(bbl.group(1)), "bbl"
    orca = _first(r"^; estimated printing time \(normal mode\) = (.*)$", tail, head)
    return (parse_duration(orca.group(1)) if orca else None), None, "orca"


def consumption_state(slots, total_grams, grams):
    """"known": at least one slot reported a positive use. "zero": the file states a weight and every reading is 0.
    "missing": nothing usable (no weight fields, unparsable values, or a total with no per-slot split): never read as free."""
    if slots:
        return "known"
    readings = list(grams) if grams else []
    stated = bool(readings) or total_grams is not None
    if stated and total_grams in (None, 0) and all(v == 0 for v in readings):
        return "zero"
    return "missing"


def parse_gcode(head, tail):
    """Parse the head and tail text of a slice; missing fields are None, never guessed."""
    head, tail = head or "", tail or ""
    seconds, model_seconds, flavour = _times(head, tail)
    slots, grams = _slots(tail, head)
    total = _first(r"^; total filament used \[g\] = (.*)$", tail, head)
    total_grams = _floats(total.group(1))[0] if total else (
        round(sum(v for v in grams if v), 2) if grams else None)
    cfg = _config(head, tail)
    model = cfg.get("printer_model", "").strip()
    return {
        "seconds": seconds,
        "model_seconds": model_seconds,
        "slots": slots,
        "consumption": consumption_state(slots, total_grams, grams),
        "total_grams": total_grams,
        "printer_model": model or None,
        "filament_presets": _split_strings(cfg.get("filament_settings_id")),
        "filament_cost": _floats(cfg.get("filament_cost")),
        "filament_density": _floats(cfg.get("filament_density")),
        "filament_notes": _split_strings(cfg.get("filament_notes")),
        "filament_colour": _split_strings(cfg.get("filament_colour")),
        "filament_type": _split_strings(cfg.get("filament_type")),
        "flavour": flavour,
    }


# ---------------------------------------------------------- slice_info (T3.1)

def _num(text):
    try:
        value = float(text)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _nonneg(text):
    """A weight or length: a negative one is unreadable (the engine refuses negatives), not a credit."""
    value = _num(text)
    return value if value is not None and value >= 0 else None


def _int(text):
    value = _num(text)
    return int(value) if value is not None else None


def _plate(node, position):
    meta = {m.get("key"): m.get("value") for m in node.findall("metadata")}
    original = _int(meta.get("index"))
    if original is None or original < 1:  # plates are numbered from 1; 0 or less would become plate -1
        original = position
    prediction = _num(meta.get("prediction"))
    filaments = []
    for item in node.findall("filament"):
        color = item.get("color") or ""
        filaments.append({
            "id": _int(item.get("id")),
            "used_g": _nonneg(item.get("used_g")),
            "used_m": _nonneg(item.get("used_m")),
            "type": (item.get("type") or "")[:50] or None,
            "color": color if re.fullmatch(r"#[0-9A-Fa-f]{6}(?:[0-9A-Fa-f]{2})?", color) else None,
        })
    return {
        "index": original - 1,
        "source_index": original,
        "prediction": int(round(prediction)) if prediction is not None else None,
        "filaments": filaments,
    }


def parse_slice_info(xml_text):
    """`Metadata/slice_info.config` text -> list of plate dicts. DOCTYPE/ENTITY is rejected."""
    if not isinstance(xml_text, str):
        raise CoreError("bad_xml", "text expected")
    if len(xml_text) > SLICE_INFO_CAP:
        raise CoreError("too_large", "slice_info")
    if re.search(r"<!\s*(DOCTYPE|ENTITY)", xml_text, re.I):
        raise CoreError("bad_xml", "DOCTYPE not allowed")
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise CoreError("bad_xml", str(exc)) from exc
    plates = [_plate(node, pos) for pos, node in enumerate(root.iter("plate"), start=1)]
    if len({p["index"] for p in plates}) < len(plates):
        # A repeated plate number: the UI keys plate controls by index, so use file order instead. `index` is 0-based like
        # every HostPlate (the UI shows index + 1); each plate's time and filament were already read from its own node.
        plates = [{**p, "index": pos} for pos, p in enumerate(plates)]
    return plates


# What zipfile raises on encrypted entries, unknown compression, bad deflate/bz2/lzma data and lying headers.
_ZIP_ERRORS = (zipfile.BadZipFile, zipfile.LargeZipFile, RuntimeError, NotImplementedError, OSError, EOFError,
               zlib.error, struct.error)


def _open_zip(data):
    """ZipFile over `data`, after checking the end record so a huge central directory is refused before
    zipfile parses it (it walks the whole directory on open). Zip64 counts exceed the caps, so they are refused."""
    if not isinstance(data, (bytes, bytearray)):
        raise CoreError("bad_zip", "bytes expected")
    end = data.rfind(b"PK\x05\x06", max(0, len(data) - 22 - 65535))
    if end < 0 or end + 22 > len(data):
        raise CoreError("bad_zip", "no end record")
    count, cd_size = struct.unpack_from("<HI", data, end + 10)
    if count > ZIP_ENTRY_CAP or cd_size > ZIP_CD_CAP:
        raise CoreError("bad_zip", "too many entries")
    box = zipfile.ZipFile(io.BytesIO(data))
    if len(box.filelist) > ZIP_ENTRY_CAP:
        box.close()
        raise CoreError("bad_zip", "too many entries")
    return box


def _slice_info(box):
    try:
        info = box.getinfo("Metadata/slice_info.config")
    except KeyError:
        return []
    if info.file_size > SLICE_INFO_CAP:
        raise CoreError("too_large", "slice_info.config")
    with box.open(info) as fh:
        raw = fh.read(SLICE_INFO_CAP + 1)  # header size can lie; the read is bounded
    if len(raw) > SLICE_INFO_CAP:
        raise CoreError("too_large", "slice_info.config")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CoreError("bad_xml", "not utf-8") from exc
    return parse_slice_info(text)


def read_sliced_3mf(data):
    """Bytes of a `.gcode.3mf` -> (plates, project filament fields), opening the zip once, in memory.
    Missing slice_info -> no plates; project fields are best effort. Raises CoreError."""
    try:
        with _open_zip(data) as box:
            return _slice_info(box), _project_filaments(box)
    except _ZIP_ERRORS as exc:
        raise CoreError("bad_zip", str(exc)) from exc


def _project_filaments(box):
    """Per-slot filament fields from `Metadata/project_settings.config` (JSON, lists of strings), keyed like
    `parse_gcode`. Best effort: {} when absent or unreadable."""
    try:
        with box.open("Metadata/project_settings.config") as fh:
            raw = fh.read(JSON_FILE_CAP + 1)
        cfg = json.loads(raw.decode("utf-8-sig")) if len(raw) <= JSON_FILE_CAP else None
    except (KeyError, ValueError, RecursionError, *_ZIP_ERRORS):  # the import still works without it
        return {}
    if not isinstance(cfg, dict):
        return {}

    def strings(key):
        value = cfg.get(key)
        return [v if isinstance(v, str) else "" for v in value] if isinstance(value, list) else None

    costs = strings("filament_cost")
    return {
        "filament_presets": strings("filament_settings_id"),
        "filament_cost": [_num(v) for v in costs] if costs is not None else None,
        "filament_notes": strings("filament_notes"),
        "filament_colour": strings("filament_colour"),
        "filament_type": strings("filament_type"),
    }


# ------------------------------------------------------------ Spoolman (T3.2)

def normalize_base_url(text):
    """User text -> `scheme://host[:port][/prefix]`. Raises ValueError(code): empty, invalid,
    scheme, credentials, host, port."""
    text = (text or "").strip() if isinstance(text, str) else ""
    if not text:
        raise ValueError("empty")
    if re.search(r"[\s\x00-\x1f\x7f]", text):
        raise ValueError("invalid")
    if "://" not in text:
        text = "http://" + text  # "localhost:7912" is the common way to type it
    parts = urllib.parse.urlsplit(text)
    if parts.scheme.lower() not in ("http", "https"):
        raise ValueError("scheme")
    if "@" in parts.netloc or parts.username is not None or parts.password is not None:
        raise ValueError("credentials")
    try:
        port = parts.port
    except ValueError as exc:
        raise ValueError("port") from exc
    host = parts.hostname
    if not host:
        raise ValueError("host")
    netloc = "[%s]" % host if ":" in host else host
    if port is not None:
        netloc += ":%d" % port
    path = re.sub(r"/api/v1/?$", "", parts.path.rstrip("/"), flags=re.I).rstrip("/")
    return "%s://%s%s" % (parts.scheme.lower(), netloc, path)


def _map_fetch_error(exc):
    if isinstance(exc, CoreError):
        return exc
    if isinstance(exc, urllib.error.HTTPError):
        return CoreError("http_%d" % exc.code, str(exc.reason))
    reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
    if isinstance(reason, PermissionError):
        return CoreError("denied", str(reason))
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return CoreError("timeout", str(reason))
    if isinstance(exc, (json.JSONDecodeError, UnicodeDecodeError, RecursionError)):
        return CoreError("bad_json", str(exc))
    return CoreError("unreachable", str(reason))


def _origin(url):
    parts = urllib.parse.urlsplit(url)
    scheme = parts.scheme.lower()
    try:
        port = parts.port or {"http": 80, "https": 443}.get(scheme)
    except ValueError:
        port = -1
    return scheme, (parts.hostname or "").lower(), port


class _SameOriginRedirect(urllib.request.HTTPRedirectHandler):
    """Follow a redirect only when scheme, host and port all stay the same: no cross-host GET, no
    https->http downgrade, no ftp/file hop. Checked before the new request is made."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if _origin(newurl) != _origin(req.full_url):
            raise CoreError("redirected", "")
        return super().redirect_request(req, fp, code, msg, headers, newurl)

    def http_error_302(self, req, fp, code, msg, headers):
        # urllib refuses file:// etc. with its own HTTPError before redirect_request; keep one code for all.
        new = headers.get("location") or headers.get("uri")
        if new is not None and _origin(urllib.parse.urljoin(req.full_url, new)) != _origin(req.full_url):
            fp.close()
            raise CoreError("redirected", "")
        return super().http_error_302(req, fp, code, msg, headers)

    http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302


open_url = urllib.request.build_opener(_SameOriginRedirect).open


def _read_capped(resp, cap, end):
    """Read in chunks until EOF, the size cap or the deadline. `read1` returns after one socket read,
    so a trickling server cannot hold a single call past one per-op timeout."""
    read = getattr(resp, "read1", None) or resp.read
    buf = bytearray()
    while True:
        if clock() > end:
            raise CoreError("timeout", "deadline")
        chunk = read(64 * 1024)
        if not chunk:
            return bytes(buf)
        buf += chunk
        if len(buf) > cap:
            raise CoreError("too_large", "response")


def _get_json(base, path, opener, timeout, end):
    url = base + path
    try:
        left = end - clock()
        if left <= 0:
            raise CoreError("timeout", "deadline")
        with opener(urllib.request.Request(url, headers={"Accept": "application/json"}),
                    timeout=min(timeout, left)) as resp:
            final = resp.geturl() if hasattr(resp, "geturl") else url
            raw = _read_capped(resp, SPOOLMAN_MAX_BYTES, end)
        if _origin(final) != _origin(url):  # second line of defence for openers without the handler
            raise CoreError("redirected", "")
        return json.loads(raw.decode("utf-8"))
    except (CoreError, urllib.error.URLError, OSError, http.client.HTTPException,
            ValueError, RecursionError) as exc:
        raise _map_fetch_error(exc) from exc


def _text(value, limit):
    return value[:limit] if isinstance(value, str) else None


def _money(value):
    """Finite non-negative number or None. Bools are not numbers."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) and value >= 0 else None


def _row_id(row):
    value = row.get("id")
    return value if isinstance(value, int) and not isinstance(value, bool) else None


ORCA_PRESET_FIELD = "orca_filament_preset"  # Spoolman extra field Spooler and U1 Control write: the Orca preset it fits


def _extra_text(row, key):
    """A Spoolman extra field as text. Extra values are JSON-encoded (`"\\"Generic PLA\\""`); blank or bad -> None."""
    extra = row.get("extra")
    value = extra.get(key) if isinstance(extra, dict) else None
    if isinstance(value, str) and value.startswith('"'):
        try:
            value = json.loads(value)
        except ValueError:
            return None
    return (value.strip()[:200] or None) if isinstance(value, str) else None


def _filament_row(row):
    if not isinstance(row, dict) or _row_id(row) is None:
        return None
    vendor = row.get("vendor")
    color = row.get("color_hex")
    return {
        "id": row["id"],
        "name": _text(row.get("name"), 200),
        "vendor": _text(vendor.get("name"), 200) if isinstance(vendor, dict) else None,
        "material": _text(row.get("material"), 100),
        "price": _money(row.get("price")),
        "weight": _money(row.get("weight")),
        "color_hex": color if isinstance(color, str) and re.fullmatch(r"[0-9A-Fa-f]{6}", color) else None,
        "orca_preset": _extra_text(row, ORCA_PRESET_FIELD),
    }


def _spool_row(row):
    if not isinstance(row, dict) or _row_id(row) is None:
        return None
    nested = row.get("filament")
    filament_id = row.get("filament_id")
    if filament_id is None and isinstance(nested, dict):
        filament_id = nested.get("id")
    if isinstance(filament_id, bool) or not isinstance(filament_id, int):
        return None
    return {
        "id": row["id"],
        "filament_id": filament_id,
        "price": _money(row.get("price")),
        "initial_weight": _money(row.get("initial_weight")),
        "remaining_weight": _money(row.get("remaining_weight")),
        "archived": row.get("archived") is True,
        "last_used": _text(row.get("last_used"), 64),
        "orca_preset": _extra_text(row, ORCA_PRESET_FIELD),
    }


def _rows(payload, convert, path):
    if not isinstance(payload, list):
        raise CoreError("bad_json", "%s: list expected" % path)
    good = [r for r in map(convert, payload) if r is not None]
    return good, len(payload) - len(good)


def _currency(base, opener, timeout, end):
    """Spoolman stores the code JSON-encoded (`"\\"BRL\\""`). Unset or invalid -> None."""
    try:
        payload = _get_json(base, "/api/v1/setting/currency", opener, timeout, end)
    except CoreError as exc:
        if exc.code == "http_404":
            return None
        raise
    if not isinstance(payload, dict) or payload.get("is_set") is False:
        return None
    value = payload.get("value")
    if isinstance(value, str) and value.startswith('"'):
        try:
            value = json.loads(value)
        except ValueError:
            return None
    if isinstance(value, str) and re.fullmatch(r"[A-Za-z]{3}", value.strip()):
        return value.strip().upper()
    return None


def _base(base_url):
    try:
        return normalize_base_url(base_url)
    except ValueError as exc:
        raise CoreError("bad_url", str(exc)) from exc


def spoolman_probe(base_url, opener=None):
    """One short `/api/v1/info` GET. Run on Orca's UI thread so its network prompt can appear;
    bounded by PROBE_DEADLINE (+ one PROBE_TIMEOUT). Raises CoreError."""
    _get_json(_base(base_url), "/api/v1/info", opener or open_url, PROBE_TIMEOUT, clock() + PROBE_DEADLINE)


def spoolman_fetch(base_url, opener=None, timeout=SPOOLMAN_TIMEOUT, deadline=SPOOLMAN_DEADLINE):
    """Read-only GETs against Spoolman. Raises CoreError. Malformed rows are skipped and counted.
    One `deadline` (seconds) covers every request and read; redirects leaving the origin are refused
    before they are followed (code `redirected`)."""
    base = _base(base_url)
    opener = opener or open_url
    end = clock() + deadline
    info = _get_json(base, "/api/v1/info", opener, timeout, end)
    currency = _currency(base, opener, timeout, end)
    filaments, bad_f = _rows(_get_json(base, "/api/v1/filament", opener, timeout, end),
                             _filament_row, "filament")
    # Archived spools too (flagged `archived`): a slot's picked spool that was archived is kept, a deleted one is dropped.
    spools, bad_s = _rows(_get_json(base, "/api/v1/spool?allow_archived=true", opener, timeout, end),
                          _spool_row, "spool")
    version = info.get("version") if isinstance(info, dict) else None
    return {"currency": currency, "version": _text(version, 50), "filaments": filaments,
            "spools": spools, "skipped": bad_f + bad_s}


# ------------------------------------------------------ Spooler files (T3.2)

def _read_small_json(path):
    try:
        if path.stat().st_size > JSON_FILE_CAP:
            return None
        data = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _invert_profiles(profiles, section="filaments"):
    """profiles.json `filaments` or `spools` ({"<id>": {"<printer>": "<preset>"}}) -> {preset: id}, by full
    preset name and by its last path segment."""
    out = {}
    filaments = profiles.get(section) if profiles else None
    if not isinstance(filaments, dict):
        return out
    for key, printers in filaments.items():
        if not (isinstance(key, str) and key.isdigit() and isinstance(printers, dict)):
            continue
        for value in printers.values():
            if isinstance(value, str) and value:
                out.setdefault(value, int(key))
                out.setdefault(value.rsplit("/", 1)[-1], int(key))
    return out


def read_spooler_files(datadir):
    """Spooler plugin data -> {detected, spoolman_url, preset_to_filament, preset_to_spool}. Never raises.
    `preset_to_spool` comes from profiles.json `spools` (Spooler's presets per spool), which win over the filament's."""
    result = {"detected": False, "spoolman_url": None, "preset_to_filament": {}, "preset_to_spool": {}}
    try:
        root = Path(datadir) / "spooler"
        profiles = _read_small_json(root / "profiles.json")
        mapping = _invert_profiles(profiles)
        spools = _invert_profiles(profiles, "spools")
        settings = _read_small_json(root / "spooler_settings.json") or {}
        try:
            url = normalize_base_url(settings.get("spoolman_url"))
        except ValueError:
            url = None
    except (OSError, TypeError, ValueError):
        return result
    return {"detected": bool(mapping or spools or url), "spoolman_url": url, "preset_to_filament": mapping,
            "preset_to_spool": spools}


# -------------------------------------------------------------- storage (T3.3)

def deny_listed(path):
    """Orca's sandbox deny-list: a whole path component named conf/config/secret(s)/cert(s),
    or a name ending in .conf/.ini (case-insensitive; both separators)."""
    for part in re.split(r"[\\/]", str(path)):
        low = part.lower()
        if low in _DENY_COMPONENTS or low.endswith(_DENY_SUFFIXES):
            return True
    return False


def _atomic_write(path, data):
    path = Path(path)
    tmp = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        tmp = None
    except PermissionError as exc:
        raise CoreError("denied", str(exc)) from exc
    except OSError as exc:
        raise CoreError("io", str(exc)) from exc
    finally:
        if tmp:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def _set_aside(path):
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target = path.with_name("%s.corrupt-%s" % (path.name, stamp))
    n = 1
    while target.exists():
        target = path.with_name("%s.corrupt-%s-%d" % (path.name, stamp, n))
        n += 1
    try:
        os.replace(path, target)
    except OSError as exc:
        raise CoreError("io", "cannot set aside corrupt file: %s" % exc) from exc


def load_json(path, default):
    """Parsed JSON, or a copy of `default` when absent. An unreadable or oversized file is renamed
    to `<name>.corrupt-<timestamp>` and `default` returned; it is never overwritten silently."""
    path = Path(path)
    try:
        size = path.stat().st_size
        raw = path.read_bytes() if size <= STORE_LOAD_CAP else None
    except FileNotFoundError:
        return copy.deepcopy(default)
    except PermissionError as exc:
        raise CoreError("denied", str(exc)) from exc
    except OSError as exc:
        raise CoreError("io", str(exc)) from exc
    try:
        if raw is None:
            raise ValueError("too large")
        return json.loads(raw.decode("utf-8"))
    except (ValueError, RecursionError):  # JSONDecodeError, UnicodeDecodeError, nesting bomb
        _set_aside(path)
        return copy.deepcopy(default)


def save_json(path, obj):
    """Atomic write: temp file in the same dir, fsync, os.replace. Over STORE_SAVE_CAP -> `too_large`,
    nothing written and the existing file untouched."""
    try:
        data = json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise CoreError("bad_json", str(exc)) from exc
    if len(data) > STORE_SAVE_CAP:
        raise CoreError("too_large", "%d bytes" % len(data))
    _atomic_write(path, data)


def safe_export_name(name):
    """Reduce `name` to a safe file name. Raises ValueError(code): name, extension, denied."""
    if not isinstance(name, str):
        raise ValueError("name")
    base = re.split(r"[\\/]", name)[-1]
    base = re.sub(r"[^A-Za-z0-9._-]", "_", base).lstrip(".")
    stem, ext = os.path.splitext(base)
    if ext.lower() not in EXPORT_EXTENSIONS:
        raise ValueError("extension")
    stem = stem.strip("._-")[: EXPORT_NAME_MAX - len(ext)]
    if not stem:
        raise ValueError("name")
    if re.fullmatch(r"(con|prn|aux|nul|com\d|lpt\d)", stem.split(".")[0], re.I):  # Windows: CON.x.html is CON
        stem = "_" + stem
    result = stem + ext.lower()
    if deny_listed(result) or stem.lower() in _DENY_COMPONENTS:
        raise ValueError("denied")
    return result


def write_export(storage_dir, name, text):
    """Write `text` to `<storage_dir>/exports/<safe name>`; returns the path as str."""
    if not isinstance(text, str):
        raise CoreError("bad_text", "str expected")
    data = text.encode("utf-8")
    if len(data) > EXPORT_CAP:
        raise CoreError("too_large", "export")
    folder = Path(storage_dir) / EXPORT_DIR
    if folder.is_symlink():
        raise CoreError("denied", "exports is a symlink")
    target = folder / safe_export_name(name)
    if target.parent != folder:
        raise CoreError("bad_name", name)
    _atomic_write(target, data)
    return str(target)
