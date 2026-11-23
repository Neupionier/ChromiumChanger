"""Remove the customized browser that ChromiumChanger built (the app itself is not touched).

Removes: browser registry policies, the browser's Desktop / Start-menu shortcuts, launcher files, the downloaded
browser, its cache, downloaded ad-blocker extensions and every profile's browsing data (history, cookies, logins,
generated extensions). Your ChromiumChanger settings, mods, history snapshots, AI settings and local AI models are
kept, so installing the browser again brings back the same customization.
"""
import json
import shutil
import sys
from pathlib import Path

from . import branding, policies, settings


def _brand_names():
    names = {"MyBrowser"}
    root = settings.profiles_root()
    if root.is_dir():
        for f in root.glob("*/settings.json"):
            try:
                n = json.loads(f.read_text(encoding="utf-8")).get("brand", {}).get("name")
                if isinstance(n, str) and n:
                    names.add(n)
            except Exception:
                pass
    return names


def describe():
    """Human readable list of what would be removed."""
    return ["The customized browser (downloaded program and its cache)",
            "Browsing data of every profile: history, cookies, saved logins, bookmarks",
            "Downloaded ad-blocker extensions",
            "Browser registry policies (Software\\Policies\\Chromium)",
            "The browser's Desktop and Start menu shortcuts and launcher files"]


def _rm(path, log):
    path = Path(path)
    try:
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()
        else:
            return
        log(f"Removed {path}")
    except OSError as e:
        log(f"WARNING: could not remove {path}: {e} (is the browser still running?)")


def run(log=print):
    names = _brand_names()          # read before anything is deleted
    policies.remove(log)
    if sys.platform == "win32":
        for folder in (branding._desktop(), branding._start_menu()):
            if folder and folder.is_dir():
                for n in names:
                    _rm(folder / f"{n}.lnk", log)
    for pattern in ("Launch *.bat", "Launch *.lnk", ".launch.lnk"):
        for f in settings.APPDIR.glob(pattern):
            _rm(f, log)
    work = settings.WORK
    for sub in ("browser", "cache", "extensions"):
        _rm(work / sub, log)
    root = settings.profiles_root()
    if root.is_dir():
        for prof in root.iterdir():
            for sub in ("userdata", "ext"):
                _rm(prof / sub, log)
    log("The customized browser was removed. ChromiumChanger and your settings were kept.")
