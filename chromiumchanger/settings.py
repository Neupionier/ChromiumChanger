"""Settings, profiles layout and workspace paths.

Layout (WORK = workspace folder):
  app.json                      global config (active profile, AI provider)
  browser/  cache/              shared by all profiles
  profiles/<name>/settings.json per-profile settings
  profiles/<name>/mods/         per-profile mods
  profiles/<name>/history/      per-profile change snapshots
  profiles/<name>/ext/          generated extension + theme
  profiles/<name>/userdata/     browser user data (bookmarks, cookies, ...)
"""
import copy
import json
import os
import re
import shutil
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
FROZEN = bool(getattr(sys, "frozen", False))
# Installed (.exe) builds keep data in %LOCALAPPDATA%; source runs keep it beside the code.
APPDIR = (Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "ChromiumChanger") if FROZEN else PROJECT
WORK = Path(os.environ.get("CC_WORKSPACE", APPDIR / "workspace"))

PROFILE_RE = re.compile(r"^[\w][\w .\-]{0,29}$")

DEFAULTS = {
    "brand": {"name": "MyBrowser", "icon": ""},
    "google_removal": True,
    "search": {
        "name": "DuckDuckGo",
        "keyword": "ddg",
        "url": "https://duckduckgo.com/?q={searchTerms}",
        "suggest_url": "",
    },
    "homepage": "about:blank",
    "shortcuts": {"desktop": True, "start_menu": True},
    "adblock": {
        "enabled": True,
        "engine": "ublock_lite",   # ublock_lite | adguard | ublock_origin | custom
        "custom_path": "",
    },
    "privacy": {
        "fingerprint": True,
        "webrtc_protect": True,
        "block_third_party_cookies": True,
        "do_not_track": True,
    },
    "appearance": {"dark_mode": True, "theme_color": "#1e1e2e", "custom_css": ""},
    "site_rules": {"block": [], "allow": []},
    "newtab": {"enabled": False, "title": "", "search": True, "clock": True, "clock_24h": True,
               "shortcuts": []},   # shortcuts: "Name | https://address"
    "developer": {
        "auto_open_devtools": False,
        "insecure_localhost": False,
        "enable_logging": False,
        "devtools_experiments": False,
        "disable_cache": False,
    },
    "flags": [],
}

AI_DEFAULTS = {"provider": "none", "model": "", "base_url": "", "api_key": ""}
APP_DEFAULTS = {"active_profile": "default", "ai": AI_DEFAULTS, "update_repo": ""}

_active = None


def deep_merge(base, over):
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


# ---------- global app config ----------

def _app_file():
    WORK.mkdir(parents=True, exist_ok=True)
    return WORK / "app.json"


def app_config():
    f = _app_file()
    if f.exists():
        try:
            return deep_merge(APP_DEFAULTS, json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass
    return copy.deepcopy(APP_DEFAULTS)


def save_app_config(c):
    _app_file().write_text(json.dumps(c, indent=2, ensure_ascii=False), encoding="utf-8")


def load_ai():
    return app_config()["ai"]


def save_ai(cfg):
    c = app_config()
    c["ai"] = deep_merge(AI_DEFAULTS, cfg)
    save_app_config(c)


# ---------- profiles ----------

def profiles_root():
    return WORK / "profiles"


def valid_profile_name(name):
    return bool(PROFILE_RE.match(name or "")) and not name.endswith((" ", "."))


def active():
    global _active
    if _active is None:
        _active = app_config()["active_profile"]
    return _active


def set_active(name):
    global _active
    if not valid_profile_name(name) or not (profiles_root() / name).is_dir():
        raise ValueError(f"Unknown profile: {name}")
    _active = name
    c = app_config()
    c["active_profile"] = name
    save_app_config(c)


def init():
    """Call once at startup: migrate the old single-profile layout, make sure a profile exists."""
    global _active
    WORK.mkdir(parents=True, exist_ok=True)
    root = profiles_root()
    old_settings = WORK / "settings.json"
    if not root.exists() and (old_settings.exists() or (WORK / "profile").exists()):
        dest = root / "default"
        dest.mkdir(parents=True)
        for old, new in (("settings.json", "settings.json"), ("mods", "mods"),
                         ("history", "history"), ("profile", "userdata")):
            src = WORK / old
            if src.exists():
                try:
                    shutil.move(str(src), str(dest / new))
                except Exception as e:  # e.g. browser still running
                    print(f"Migration of {old} failed: {e}")
        shutil.rmtree(WORK / "ext", ignore_errors=True)  # regenerated on Apply
        # AI config used to live in settings.json
        try:
            old = json.loads((dest / "settings.json").read_text(encoding="utf-8"))
            if old.get("ai"):
                c = app_config()
                c["ai"] = deep_merge(AI_DEFAULTS, {k: v for k, v in old["ai"].items() if k in AI_DEFAULTS})
                if not c["ai"].get("api_key"):
                    c["ai"]["provider"] = "none"  # AI is opt-in now
                save_app_config(c)
        except Exception:
            pass
    root.mkdir(parents=True, exist_ok=True)
    if not any(p.is_dir() for p in root.iterdir()):
        (root / "default").mkdir()
    names = sorted(p.name for p in root.iterdir() if p.is_dir())
    c = app_config()
    if c["active_profile"] not in names:
        c["active_profile"] = names[0]
        save_app_config(c)
    _active = None


def paths():
    prof = profiles_root() / active()
    d = {
        "work": WORK,
        "browser": WORK / "browser",
        "cache": WORK / "cache",
        "profile_dir": prof,
        "profile": prof / "userdata",
        "ext": prof / "ext",
        "mods": prof / "mods",
        "history": prof / "history",
        "settings": prof / "settings.json",
    }
    for k, v in d.items():
        if k != "settings":
            v.mkdir(parents=True, exist_ok=True)
    return d


# ---------- per-profile settings ----------

def load():
    p = paths()["settings"]
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            data.pop("ai", None)
            return deep_merge(DEFAULTS, data)
        except Exception:
            pass
    return copy.deepcopy(DEFAULTS)


def save(s):
    s = {k: v for k, v in s.items() if k != "ai"}
    paths()["settings"].write_text(json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")
