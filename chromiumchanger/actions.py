"""High-level actions used by the GUI (and CLI)."""
from . import extsources, mods, settings, validate

MERGE_KEYS = ("brand", "google_removal", "search", "homepage", "adblock", "shortcuts",
              "privacy", "appearance", "site_rules", "newtab", "developer")


def _get(d, dotted):
    for p in dotted.split("."):
        d = d[p]
    return d


def _set(d, dotted, v):
    parts = dotted.split(".")
    for p in parts[:-1]:
        d = d[p]
    d[parts[-1]] = v


def apply_plan(plan_in):
    """Re-validate a plan the user approved, snapshot, then apply it to the active profile."""
    plan = validate.sanitize_plan(plan_in)
    mods.snapshot("Before AI change: " + plan["summary"][:60])
    s = settings.load()
    for key, val in plan["settings_patch"].items():
        _set(s, key, val)
    s["flags"] = list(dict.fromkeys(s["flags"] + plan["flags"]))
    settings.save(s)
    for m in plan["mods"]:
        m = dict(m)
        m.pop("warnings", None)
        mods.save_mod(m)
    return plan


def save_settings(new):
    """Validate and save settings edited by the user in the GUI."""
    s = settings.load()
    mods.snapshot("Before settings change")
    for k in MERGE_KEYS:
        if k in new:
            s[k] = settings.deep_merge(s[k], new[k]) if isinstance(new[k], dict) else new[k]
    flags = []
    for f in new.get("flags", s["flags"]):
        ok, why = validate.check_flag(f)
        if not ok:
            raise ValueError(f"Flag {f!r} rejected: {why}")
        flags.append(f)
    s["flags"] = flags
    for key in validate.SETTINGS_WHITELIST:
        _set(s, key, validate.clean_setting(key, _get(s, key)))
    ab = s["adblock"]
    if ab.get("engine") not in extsources.ENGINES:
        raise ValueError("Unknown ad blocker selection.")
    if not isinstance(ab.get("custom_path", ""), str) or len(ab["custom_path"]) > 500:
        raise ValueError("Invalid custom extension path.")
    if not isinstance(s["brand"].get("icon", ""), str):
        raise ValueError("brand.icon must be text")
    settings.save(s)
    return s
