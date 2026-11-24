"""Generate the built-in extension (ad blocker + mods) and the theme extension loaded by the browser."""
import json
from urllib.parse import urlparse
import shutil
import time

from . import settings, validate
from .mods import list_mods


def _luma(hexcolor):
    r, g, b = (int(hexcolor[i:i + 2], 16) for i in (1, 3, 5))
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255, (r, g, b)


NEWTAB_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>New Tab</title>
<link rel="stylesheet" href="newtab.css"></head>
<body><main>
<div id="clock" hidden><div id="time"></div><div id="date"></div></div>
<h1 id="title" hidden></h1>
<form id="search" hidden><input id="q" type="text" autocomplete="off" autofocus placeholder="Search"></form>
<nav id="tiles"></nav>
</main>
<script src="config.js"></script><script src="newtab.js"></script></body></html>
"""

NEWTAB_CSS = """html,body{margin:0;height:100%;background:var(--bg);color:var(--fg);font-family:"Segoe UI",system-ui,sans-serif}
main{min-height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:22px;padding:24px;box-sizing:border-box}
#time{font-size:72px;font-weight:300;letter-spacing:2px;text-align:center}
#date{font-size:16px;opacity:.7;text-align:center;margin-top:4px}
h1{font-size:22px;font-weight:400;margin:0;opacity:.9;text-align:center}
#search{width:min(640px,92vw)}
#q{width:100%;box-sizing:border-box;padding:14px 20px;font-size:17px;border-radius:26px;border:1px solid var(--line);background:var(--card);color:var(--fg);outline:none}
#q:focus{border-color:var(--acc)}
#tiles{display:flex;flex-wrap:wrap;gap:14px;justify-content:center;max-width:760px}
#tiles a{display:flex;flex-direction:column;align-items:center;gap:8px;width:96px;padding:14px 6px;border-radius:14px;background:var(--card);color:var(--fg);text-decoration:none;font-size:13px}
#tiles a:hover{background:var(--line)}
#tiles .ico{width:42px;height:42px;border-radius:50%;background:var(--acc);color:var(--bg);display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:600}
#tiles .nm{max-width:90px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
"""

NEWTAB_JS = """(function(){
var C=window.CC_NEWTAB||{};
var r=document.documentElement.style;
r.setProperty("--bg",C.bg);r.setProperty("--fg",C.fg);r.setProperty("--card",C.card);r.setProperty("--line",C.line);r.setProperty("--acc",C.acc);
function $(i){return document.getElementById(i);}
if(C.title){var h=$("title");h.textContent=C.title;h.hidden=false;}
if(C.clock){
  $("clock").hidden=false;
  var tick=function(){var d=new Date();
    $("time").textContent=d.toLocaleTimeString([],{hour:"2-digit",minute:"2-digit",hour12:!C.clock24});
    $("date").textContent=d.toLocaleDateString([],{weekday:"long",year:"numeric",month:"long",day:"numeric"});};
  tick();setInterval(tick,1000);
}
if(C.search){
  var f=$("search");f.hidden=false;
  f.addEventListener("submit",function(e){e.preventDefault();var t=$("q").value.trim();if(!t)return;
    if(window.chrome&&chrome.search&&chrome.search.query){chrome.search.query({text:t,disposition:"CURRENT_TAB"});}
    else if(C.searchUrl){location.href=C.searchUrl.replace("{searchTerms}",encodeURIComponent(t));}});
}
(C.shortcuts||[]).forEach(function(s){
  var a=document.createElement("a");a.href=s.url;
  var i=document.createElement("div");i.className="ico";i.textContent=(s.name||"?").charAt(0).toUpperCase();
  var n=document.createElement("div");n.className="nm";n.textContent=s.name;
  a.appendChild(i);a.appendChild(n);$("tiles").appendChild(a);
});
})();
"""


def build_newtab(s, d, manifest):
    """Optional New Tab page (search box, clock, shortcuts) shipped inside the built-in extension.

    Everything is local: no remote scripts, no network requests. The search box uses the browser's default
    search engine through chrome.search.query.
    """
    nt = s.get("newtab", {})
    if not nt.get("enabled"):
        return False
    ap = s["appearance"]
    luma, rgb = _luma(ap["theme_color"])
    dark = bool(ap.get("dark_mode", True)) or luma < 0.55
    bg = ap["theme_color"] if dark else "#f4f5f8"
    fg = "#f2f3f8" if dark else "#1b1d27"
    card = "rgba(255,255,255,.09)" if dark else "rgba(0,0,0,.06)"
    line = "rgba(255,255,255,.2)" if dark else "rgba(0,0,0,.15)"
    shortcuts = []
    for e in nt.get("shortcuts", [])[:12]:
        try:
            name, url = validate.parse_shortcut(e)
        except ValueError:
            continue
        shortcuts.append({"name": name, "url": url})
    se = s["search"]
    cfg = {"bg": bg, "fg": fg, "card": card, "line": line, "acc": "#7c8cff",
           "title": str(nt.get("title", ""))[:80], "clock": bool(nt.get("clock", True)),
           "clock24": bool(nt.get("clock_24h", True)), "search": bool(nt.get("search", True)),
           "searchUrl": se["url"] if str(se.get("url", "")).startswith("https://") else "",
           "shortcuts": shortcuts}
    nd = d / "newtab"
    nd.mkdir(parents=True, exist_ok=True)
    (nd / "newtab.html").write_text(NEWTAB_HTML, encoding="utf-8")
    (nd / "newtab.css").write_text(NEWTAB_CSS, encoding="utf-8")
    (nd / "newtab.js").write_text(NEWTAB_JS, encoding="utf-8")
    (nd / "config.js").write_text("window.CC_NEWTAB = " + json.dumps(cfg, ensure_ascii=True) + ";\n", encoding="utf-8")
    manifest["chrome_url_overrides"] = {"newtab": "newtab/newtab.html"}
    manifest["permissions"] = sorted(set(manifest.get("permissions", [])) | {"search"})
    return True


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

    if build_newtab(s, d, manifest):
        log("New tab page enabled (search box / clock / shortcuts).")

    (d / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return d
