"""Download and extract ungoogled-chromium (Windows portable zip)."""
import hashlib
import json
import platform
import shutil
import urllib.request
import zipfile
from pathlib import Path

from . import settings

API = "https://api.github.com/repos/ungoogled-software/ungoogled-chromium-windows/releases/latest"


def _arch():
    m = platform.machine().lower()
    return "arm64" if "arm" in m or "aarch" in m else "x64"


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "ChromiumChanger"})
    return urllib.request.urlopen(req, timeout=60)


def find_exe():
    b = settings.paths()["browser"]
    for p in b.rglob("chrome.exe"):
        return p
    return None


def installed_version():
    f = settings.paths()["browser"] / "version.json"
    return json.loads(f.read_text()) if f.exists() else None


def install(log=print):
    b = settings.paths()["browser"]
    log("Checking the latest release...")
    with _get(API) as r:
        rel = json.loads(r.read().decode())
    suffix = f"_windows_{_arch()}.zip"
    asset = next((a for a in rel["assets"] if a["name"].endswith(suffix)), None)
    if not asset:
        raise RuntimeError(f"Portable zip ({suffix}) not found in the release")
    log(f"Downloading: {asset['name']} ({asset['size'] // 1048576} MB)")
    zpath = settings.paths()["cache"] / asset["name"]
    h = hashlib.sha256()
    done = 0
    with _get(asset["browser_download_url"]) as r, open(zpath, "wb") as f:
        last = -1
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            h.update(chunk)
            done += len(chunk)
            pct = done * 100 // max(asset["size"], 1)
            if pct // 10 != last:
                last = pct // 10
                log(f"  {pct}%")
    digest = (asset.get("digest") or "").removeprefix("sha256:")
    if digest and digest.lower() != h.hexdigest():
        zpath.unlink()
        raise RuntimeError("SHA-256 checksum mismatch. The download was discarded.")
    log("Checksum verified" if digest else "(no checksum in the release, verification skipped)")

    if b.exists():
        shutil.rmtree(b)
    b.mkdir(parents=True)
    log("Extracting...")
    root = b.resolve()
    with zipfile.ZipFile(zpath) as z:
        for m in z.infolist():
            target = (root / m.filename).resolve()
            if root not in target.parents and target != root:
                raise RuntimeError("Suspicious zip path (zip-slip) detected")
        z.extractall(root)
    (b / "version.json").write_text(json.dumps({"tag": rel["tag_name"], "asset": asset["name"]}))
    exe = find_exe()
    if not exe:
        raise RuntimeError("chrome.exe not found")
    log(f"Install complete: {exe}")
    return exe
