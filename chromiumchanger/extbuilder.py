"""Generate the built-in extension (ad blocker + mods) and the theme extension loaded by the browser."""
import json
from urllib.parse import urlparse
import shutil
import time

from . import settings
from .mods import list_mods


def _luma(hexcolor):
    r, g, b = (int(hexcolor[i:i + 2], 16) for i in (1, 3, 5))
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255, (r, g, b)


def build_theme(s):
    p = settings.paths()
    d = p["ext"] / "theme"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    luma, rgb = _luma(s["appearance"]["theme_color"])
    text = [255, 255, 255] if luma < 0.55 else [20, 20, 20]
    lighter = [min(255, c + 25) for c in rgb] if luma < 0.55 else [max(0, c - 15) for c in rgb]
    manifest = {
        "manifest_version": 3,
        "name": f"{s['brand']['name']} Theme",
        "version": "1.0",
        "theme": {"colors": {
            "frame": list(rgb), "frame_inactive": list(rgb),
            "toolbar": lighter, "tab_text": text, "tab_background_text": text,
            "bookmark_text": text, "ntp_background": list(rgb), "ntp_text": text,
            "button_background": lighter,
        }},
    }
    (d / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return d


def build_core(s, log=print):
    p = settings.paths()
    d = p["ext"] / "core"
    if d.exists():
        shutil.rmtree(d)
    (d / "mods").mkdir(parents=True)
    (d / "rules").mkdir()

    manifest = {
        "manifest_version": 3,
        "name": f"{s['brand']['name']} Core",
        "version": f"1.0.0.{int(time.time()) % 65000}",
        "description": "ChromiumChanger built-in extension: user mods and custom CSS",
        "permissions": [],
        "content_scripts": [],
    }

    # Default search engine / home page through the extension. The matching registry policies are ignored by
    # the browser on Windows PCs that are not domain-joined or MDM-enrolled ("This policy is blocked"), but
    # extension settings overrides work everywhere.
    se = s["search"]
    ov = {}
    if "{searchTerms}" in (se.get("url") or "") and se["url"].startswith("https://"):
        host = urlparse(se["url"]).netloc
        sp = {"name": se.get("name") or host, "keyword": se.get("keyword") or host,
              "search_url": se["url"], "favicon_url": f"https://{host}/favicon.ico",
              "encoding": "UTF-8", "is_default": True}
        if (se.get("suggest_url") or "").startswith("https://"):
            sp["suggest_url"] = se["suggest_url"]
        ov["search_provider"] = sp
    hp = s.get("homepage") or ""
    if hp.startswith(("http://", "https://")):
        ov["homepage"] = hp
        ov["startup_pages"] = [hp]
    if ov:
        manifest["chrome_settings_overrides"] = ov
        log(f"Default search engine / home page set by the built-in extension: {se.get('name')}")

    custom = s["appearance"].get("custom_css", "").strip()
    if custom:
        (d / "mods" / "_custom.css").write_text(custom, encoding="utf-8")
        manifest["content_scripts"].append({
            "matches": ["<all_urls>"], "css": ["mods/_custom.css"], "run_at": "document_start"})

    for m in list_mods():
        if not m.get("enabled", True):
            continue
        cs = {"matches": m["matches"], "run_at": m["run_at"]}
        if m.get("css", "").strip():
            (d / "mods" / f"{m['id']}.css").write_text(m["css"], encoding="utf-8")
            cs["css"] = [f"mods/{m['id']}.css"]
        if m.get("js", "").strip():
            (d / "mods" / f"{m['id']}.js").write_text(m["js"], encoding="utf-8")
            cs["js"] = [f"mods/{m['id']}.js"]
        if "css" in cs or "js" in cs:
            manifest["content_scripts"].append(cs)

    (d / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return d
