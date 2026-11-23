"""Export / import a profile's settings and mods as a single .ccprofile (JSON) file.

Browsing data (bookmarks, cookies, passwords) and API keys are never exported.
Imported files are untrusted: everything is re-validated, and mods that contain
JavaScript are imported DISABLED until the user reviews and enables them.
"""
import json
import uuid
from pathlib import Path

from . import extsources, mods, profiles, settings, validate

FORMAT = "chromiumchanger-profile"
MAX_BYTES = 5_000_000


def export_profile(dest):
    s = settings.load()
    s.pop("ai", None)
    s["brand"] = {"name": s["brand"]["name"], "icon": ""}  # icon path is machine specific
    data = {
        "format": FORMAT,
        "version": 1,
        "name": settings.active(),
        "settings": s,
        "mods": [{k: v for k, v in m.items() if k != "id"} for m in mods.list_mods()],
    }
    Path(dest).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return len(data["mods"])


def _clean_settings(raw):
    """Keep only validated values; everything else falls back to defaults."""
    out = settings.deep_merge(settings.DEFAULTS, {})
    issues = []
    wanted = {}
    for key in validate.SETTINGS_WHITELIST:
        node, ok = raw, True
        for part in key.split("."):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                ok = False
                break
        if ok:
            wanted[key] = node
    patch = {}
    for key, val in wanted.items():
        try:
            patch[key] = validate.clean_setting(key, val)
        except ValueError as e:
            issues.append(str(e))
    for key, val in patch.items():
        node = out
        parts = key.split(".")
        for p in parts[:-1]:
            node = node[p]
        node[parts[-1]] = val
    for key in ("google_removal",):
        if isinstance(raw.get(key), bool):
            out[key] = raw[key]
    for k in settings.DEFAULTS["developer"]:
        v = raw.get("developer", {}).get(k)
        if isinstance(v, bool):
            out["developer"][k] = v
    flags = []
    for f in raw.get("flags", []):
        ok, why = validate.check_flag(f)
        if ok:
            flags.append(f)
        else:
            issues.append(f"Flag rejected {f!r}: {why}")
    out["flags"] = flags
    if isinstance(raw.get("adblock", {}).get("enabled"), bool):
        out["adblock"]["enabled"] = raw["adblock"]["enabled"]
    eng = raw.get("adblock", {}).get("engine")
    if eng in extsources.ENGINES and eng != "custom":  # custom paths are machine specific
        out["adblock"]["engine"] = eng
    return out, issues


def import_profile(path, name=None):
    """Create a NEW profile from a .ccprofile file. Returns a summary dict."""
    p = Path(path)
    if p.stat().st_size > MAX_BYTES:
        raise ValueError("File is too large to be a profile export.")
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise ValueError("This is not a ChromiumChanger profile file.")
    base = name or str(data.get("name", "imported"))
    base = "".join(ch for ch in base if ch.isalnum() or ch in " ._-")[:24].strip() or "imported"
    final, n = base, 2
    while final.lower() in [x.lower() for x in profiles.list_profiles()]:
        final = f"{base}-{n}"
        n += 1
    profiles.create(final)
    pdir = settings.profiles_root() / final
    s, issues = _clean_settings(data.get("settings", {}) if isinstance(data.get("settings"), dict) else {})
    s["brand"]["name"] = f"{settings.DEFAULTS['brand']['name']}-{final}".replace(" ", "-")
    (pdir / "settings.json").write_text(json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")
    (pdir / "mods").mkdir(exist_ok=True)
    warnings, held = [], 0
    for m in (data.get("mods") or [])[:50]:
        try:
            cm, w = validate.sanitize_mod(m)
        except ValueError as e:
            issues.append(f"Mod rejected: {e}")
            continue
        has_js = bool(cm["js"].strip())
        cm.update({"id": uuid.uuid4().hex[:10], "enabled": not has_js})
        held += has_js
        warnings += [f"[{cm['name']}] {x}" for x in w]
        (pdir / "mods" / f"{cm['id']}.json").write_text(
            json.dumps(cm, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"profile": final, "warnings": warnings, "issues": issues, "held_js_mods": held}
