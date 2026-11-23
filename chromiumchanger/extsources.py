"""Download and prepare third-party ad-blocker extensions (uBlock Origin Lite, AdGuard, ...).

Extensions are downloaded from the projects' official GitHub releases, verified with the
SHA-256 digest GitHub publishes, and loaded as unpacked extensions via --load-extension.
They are shared by all profiles and kept in <workspace>/extensions/<engine>/<version>/.
"""
import hashlib
import json
import re
import shutil
import urllib.request
import zipfile
from pathlib import Path

from . import settings

SOURCES = {
    "ublock_lite": {
        "label": "uBlock Origin Lite (recommended)",
        "repo": "uBlockOrigin/uBOL-home",
        "asset": r"^uBOLite_[\d.]+\.chromium\.zip$",
    },
    "adguard": {
        "label": "AdGuard (Manifest V3)",
        "repo": "AdguardTeam/AdGuardBrowserExtension",
        "asset": r"^chrome-mv3\.zip$",
    },
    "ublock_origin": {
        "label": "uBlock Origin (full, Manifest V2 - experimental)",
        "repo": "gorhill/uBlock",
        "asset": r"^uBlock0_[\d.]+\.chromium\.zip$",
    },
}
ENGINES = list(SOURCES) + ["custom"]
LABELS = {**{k: v["label"] for k, v in SOURCES.items()},
          "custom": "Custom extension (folder or .zip)"}
MV2_FLAGS = ["--disable-features=ExtensionManifestV2Unsupported,ExtensionManifestV2Disabled",
             "--enable-features=AllowLegacyMV2Extensions"]
MAX_FILES = 20000


def root():
    d = settings.WORK / "extensions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _open(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "ChromiumChanger"}), timeout=60)


def latest(key):
    """(tag, asset) of the newest stable release that has the wanted asset."""
    src = SOURCES[key]
    with _open(f"https://api.github.com/repos/{src['repo']}/releases?per_page=15") as r:
        releases = json.loads(r.read().decode())
    pat = re.compile(src["asset"])
    for rel in releases:
        if rel.get("prerelease") or rel.get("draft"):
            continue
        for a in rel.get("assets", []):
            if pat.match(a["name"]):
                return rel["tag_name"], a
    raise RuntimeError(f"No suitable release found for {src['label']}")


def _extract(zpath, dest):
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    base = dest.resolve()
    with zipfile.ZipFile(zpath) as z:
        infos = z.infolist()
        if len(infos) > MAX_FILES:
            raise RuntimeError("Archive has too many files.")
        for m in infos:
            t = (base / m.filename).resolve()
            if base not in t.parents and t != base:
                raise RuntimeError("Suspicious path in archive (zip-slip).")
        z.extractall(base)


def find_manifest_dir(folder):
    folder = Path(folder)
    if (folder / "manifest.json").is_file():
        return folder
    for sub in sorted(p for p in folder.iterdir() if p.is_dir()):
        if (sub / "manifest.json").is_file():
            return sub
    return None


def manifest_info(path):
    m = json.loads((Path(path) / "manifest.json").read_text(encoding="utf-8-sig"))
    return {"mv": int(m.get("manifest_version", 0)), "name": str(m.get("name", "")), "version": str(m.get("version", ""))}


def _current_file(key):
    return root() / key / "current.json"


def installed(key):
    f = _current_file(key)
    if f.exists():
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            if Path(d["path"]).is_dir():
                return d
        except Exception:
            pass
    return None


def install(key, log=print):
    """Download the latest release and unpack it. Returns the extension folder."""
    src = SOURCES[key]
    log(f"Looking up the latest {src['label']}...")
    tag, asset = latest(key)
    log(f"Downloading {asset['name']} ({asset['size'] // 1048576} MB)...")
    zpath = settings.paths()["cache"] / asset["name"]
    h = hashlib.sha256()
    with _open(asset["browser_download_url"]) as r, open(zpath, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            h.update(chunk)
    digest = (asset.get("digest") or "").removeprefix("sha256:")
    if digest and digest.lower() != h.hexdigest():
        zpath.unlink()
        raise RuntimeError("SHA-256 checksum mismatch. The download was discarded.")
    log("Checksum verified." if digest else "(no checksum published, verification skipped)")
    dest = root() / key / re.sub(r"[^\w.\-]", "_", tag)
    if dest.exists():
        shutil.rmtree(dest)
    _extract(zpath, dest)
    mdir = find_manifest_dir(dest)
    if not mdir:
        raise RuntimeError("manifest.json not found in the downloaded extension.")
    info = manifest_info(mdir)
    _current_file(key).write_text(json.dumps({"tag": tag, "path": str(mdir), **info}), encoding="utf-8")
    for old in (root() / key).iterdir():  # drop older versions
        if old.is_dir() and old != dest:
            shutil.rmtree(old, ignore_errors=True)
    log(f"Installed {src['label']} {info['version']} (Manifest V{info['mv']}).")
    return str(mdir)


def _prepare_custom(path, log):
    p = Path(path).expanduser()
    if p.is_file() and p.suffix.lower() == ".zip":
        key = hashlib.sha1(f"{p}|{p.stat().st_mtime_ns}".encode()).hexdigest()[:10]
        dest = root() / "custom" / key
        if not dest.exists():
            _extract(p, dest)
        folder = find_manifest_dir(dest)
    elif p.is_dir():
        folder = find_manifest_dir(p)
    else:
        raise RuntimeError(f"Custom extension path not found: {path}")
    if not folder:
        raise RuntimeError("manifest.json not found in the custom extension.")
    return str(folder)


def prepare(s, log=print):
    """Decide which ad-blocker extension to load. Never raises: on failure the browser starts without one."""
    ab = s["adblock"]
    result = {"engine": "none", "path": None, "flags": []}
    if not ab.get("enabled"):
        result["engine"] = "none"
        return result
    engine = ab.get("engine", "ublock_lite")
    if engine not in SOURCES and engine != "custom":  # e.g. the removed "builtin" setting
        engine = "ublock_lite"
    try:
        if engine in SOURCES:
            inst = installed(engine)
            path = inst["path"] if inst else install(engine, log)
        elif engine == "custom":
            path = _prepare_custom(ab.get("custom_path", ""), log)
        else:
            raise RuntimeError(f"Unknown ad blocker: {engine}")
        info = manifest_info(path)
        if info["mv"] == 2:
            log("WARNING: this is a Manifest V2 extension. Recent Chromium versions may refuse to load it; "
                "if it does not appear in chrome://extensions, choose uBlock Origin Lite instead.")
            result["flags"] = list(MV2_FLAGS)
        result.update(engine=engine, path=path)
    except Exception as e:
        log(f"WARNING: could not prepare the selected ad blocker ({e}). Browser will start without an ad blocker.")
    return result
