"""Self-update from GitHub Releases (packaged Windows app only).

A release must have the asset 'ChromiumChanger-win64.zip' (the zipped dist\\ChromiumChanger folder) and a tag
like v0.3.0. The download is checked against the SHA-256 digest GitHub publishes for the asset.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

from . import __version__, extsources, settings

UPDATE_REPO = "Neupionier/ChromiumChanger"   # GitHub "owner/repo" that publishes the releases
ASSET = "ChromiumChanger-win64.zip"


def repo():
    r = os.environ.get("CC_UPDATE_REPO") or settings.app_config().get("update_repo") or UPDATE_REPO
    r = (r or "").strip()
    return r if re.fullmatch(r"[\w.\-]+/[\w.\-]+", r) else ""


def _ver(tag):
    nums = re.findall(r"\d+", str(tag).split("-")[0])
    return tuple(int(n) for n in nums[:4]) or (0,)


def check(log=print):
    """Returns {"repo","tag","newer","size","url","digest","notes"}."""
    r = repo()
    if not r:
        raise RuntimeError("No update source is configured yet. Put your GitHub 'owner/repo' into "
                           "chromiumchanger/updater.py (UPDATE_REPO) or app.json (\"update_repo\").")
    log(f"Checking for updates ({r})...")
    with extsources._open(f"https://api.github.com/repos/{r}/releases/latest") as resp:
        rel = json.loads(resp.read().decode())
    asset = next((a for a in rel.get("assets", []) if a["name"] == ASSET), None)
    if not asset:
        raise RuntimeError(f"The latest release has no {ASSET} file.")
    info = {"repo": r, "tag": rel["tag_name"], "newer": _ver(rel["tag_name"]) > _ver(__version__),
            "size": asset["size"], "url": asset["browser_download_url"],
            "digest": (asset.get("digest") or "").removeprefix("sha256:"), "notes": (rel.get("body") or "")[:1500]}
    log(f"Installed: {__version__}   Latest: {info['tag']}")
    return info


def can_self_update():
    return settings.FROZEN and sys.platform == "win32"


def download(info, log=print):
    """Download and verify the new version into a temp folder. Returns the folder containing the new exe."""
    work = Path(tempfile.mkdtemp(prefix="cc_update_"))
    zpath = work / ASSET
    log(f"Downloading {info['tag']} ({info['size'] // 1048576} MB)...")
    h = hashlib.sha256()
    with extsources._open(info["url"]) as r, open(zpath, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            h.update(chunk)
    if not info["digest"]:
        shutil.rmtree(work, ignore_errors=True)
        raise RuntimeError("The release has no published checksum, so the update was not installed.")
    if info["digest"].lower() != h.hexdigest():
        shutil.rmtree(work, ignore_errors=True)
        raise RuntimeError("SHA-256 checksum mismatch. The download was discarded.")
    log("Checksum verified. Unpacking...")
    new = work / "new"
    extsources._extract(zpath, new)
    zpath.unlink()
    folder = new if (new / "ChromiumChanger.exe").is_file() else next(
        (p for p in new.iterdir() if (p / "ChromiumChanger.exe").is_file()), None)
    if not folder:
        shutil.rmtree(work, ignore_errors=True)
        raise RuntimeError("ChromiumChanger.exe was not found in the update.")
    return str(folder)


def schedule_install(new_folder, log=print):
    """After this process exits, copy the new files over the app folder and start the app again."""
    app = Path(sys.executable).resolve().parent
    exe = app / "ChromiumChanger.exe"
    bat = Path(tempfile.gettempdir()) / "chromiumchanger_update.bat"
    bat.write_bytes((
        "@echo off\r\n"
        "set n=0\r\n"
        ":retry\r\n"
        "ping -n 3 127.0.0.1 >nul\r\n"
        f'robocopy "{new_folder}" "{app}" /E /IS /IT /R:2 /W:1 /NFL /NDL /NJH /NJS /NP >nul\r\n'
        "if %errorlevel% GEQ 8 (\r\n"
        "  set /a n+=1\r\n"
        "  if %n% LSS 20 goto retry\r\n"
        ")\r\n"
        f'start "" "{exe}"\r\n'
        f'rmdir /s /q "{Path(new_folder).parent}" 2>nul\r\n'
        '(goto) 2>nul & del "%~f0"\r\n').encode("ascii", "replace"))
    subprocess.Popen(["cmd", "/c", str(bat)], creationflags=0x08000000 | 0x00000008,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    log("The update will be installed as soon as the app closes; it restarts automatically.")
