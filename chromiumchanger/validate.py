"""Validate AI-generated plans/code before applying them. AI output is never trusted."""
import re
from urllib.parse import urlparse

FLAG_RE = re.compile(r"^--[a-z0-9][a-z0-9-]*(=[A-Za-z0-9_.,:/+\-]*)?$")
BLOCKED_FLAGS = {
    "--no-sandbox", "--disable-web-security", "--allow-running-insecure-content",
    "--ignore-certificate-errors", "--disable-site-isolation-trials",
    "--remote-debugging-port", "--remote-debugging-pipe", "--remote-allow-origins",
    "--user-data-dir", "--load-extension", "--disable-extensions-except",
    "--disable-gpu-sandbox", "--disable-setuid-sandbox", "--single-process",
    "--proxy-server", "--proxy-pac-url", "--host-resolver-rules", "--disable-features-sandbox",
    "--unsafely-treat-insecure-origin-as-secure", "--allow-file-access-from-files",
    "--enable-automation", "--headless", "--utility-cmd-prefix", "--renderer-cmd-prefix",
    "--gpu-launcher", "--ppapi-plugin-launcher", "--no-zygote",
    "--browser-subprocess-path", "--proxy-auto-detect", "--proxy-bypass-list", "--host-rules",
    "--remote-debugging-address", "--js-flags", "--ssl-key-log-file", "--log-net-log",
    "--ignore-certificate-errors-spki-list", "--reduce-security-for-testing", "--test-type",
    "--crash-server-url", "--allow-sandbox-debugging", "--disable-seccomp-filter-sandbox",
    "--auth-server-allowlist", "--auth-negotiate-delegate-allowlist", "--extension-content-verification",
    "--disable-extensions-file-access-check", "--allow-http-screen-capture", "--enable-nacl",
}
# --disable-features / --enable-features values that weaken site isolation or certificate checks
RISKY_FEATURES = re.compile(r"isolateorigins|siteperprocess|site-per-process|sitesperprocess|"
                            r"certificatetransparency|sslkeylog|strictoriginisolation", re.I)

MATCH_RE = re.compile(r"^(<all_urls>|(https?|\*)://(\*|\*\.[A-Za-z0-9.-]+|[A-Za-z0-9.-]+)/.*)$")
DOMAIN_RE = re.compile(r"^[A-Za-z0-9*.\-]+(/[A-Za-z0-9_\-./*?=&%]*)?$")
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

RISKY_JS = [
    (r"\beval\s*\(", "uses eval()"),
    (r"new\s+Function\s*\(", "uses new Function()"),
    (r"\bfetch\s*\(", "network request (fetch)"),
    (r"XMLHttpRequest", "network request (XHR)"),
    (r"\bWebSocket\b", "uses WebSocket"),
    (r"sendBeacon", "uses navigator.sendBeacon"),
    (r"document\.cookie", "accesses cookies"),
    (r"localStorage|sessionStorage|indexedDB", "accesses web storage"),
    (r"<\s*script", "injects a script tag"),
    (r"\.src\s*=\s*['\"]https?:", "loads an external resource"),
    (r"importScripts|import\s*\(", "dynamic import"),
    (r"\b(?:window|globalThis|self|top|parent|document)\s*\[", "dynamic property access (may hide API calls)"),
    (r"\batob\s*\(|fromCharCode|\\x[0-9a-fA-F]{2}|\\u[0-9a-fA-F]{4}", "encoded or obfuscated strings"),
    (r"set(?:Timeout|Interval)\s*\(\s*['\"`]", "runs code from a string"),
    (r"\[\s*['\"][A-Za-z_]+['\"]\s*\+", "builds a name from string parts"),
    (r"type\s*=\s*['\"]password['\"]|input\[type=.?password", "accesses password fields"),
]
RISKY_CSS = [
    (r"@import", "CSS @import"),
    (r"url\(\s*['\"]?https?:", "CSS loading an external URL"),
]

SETTINGS_WHITELIST = {
    "brand.name": str,
    "search.name": str, "search.keyword": str, "search.url": str, "search.suggest_url": str,
    "homepage": str,
    "adblock.enabled": bool,
    "privacy.fingerprint": bool, "privacy.webrtc_protect": bool,
    "privacy.block_third_party_cookies": bool, "privacy.do_not_track": bool,
    "appearance.dark_mode": bool, "appearance.theme_color": str, "appearance.custom_css": str,
    "site_rules.block": list, "site_rules.allow": list,
    "newtab.enabled": bool, "newtab.search": bool, "newtab.clock": bool, "newtab.clock_24h": bool,
    "newtab.title": str, "newtab.shortcuts": list,
}
SHORTCUT_NAME_RE = re.compile(r"^[\w .&+\-]{1,24}$")


def parse_shortcut(entry):
    """'Name | https://address' -> (name, url); raises ValueError."""
    if not isinstance(entry, str) or "|" not in entry:
        raise ValueError(f"newtab.shortcuts: use 'Name | https://address' ({entry!r})")
    name, url = (x.strip() for x in entry.split("|", 1))
    u = urlparse(url)
    if not SHORTCUT_NAME_RE.match(name) or u.scheme not in ("http", "https") or not u.netloc or len(url) > 500:
        raise ValueError(f"newtab.shortcuts: invalid entry {entry!r}")
    return name, url


def scan_js(code):
    return [label for pat, label in RISKY_JS if re.search(pat, code)]


def scan_css(code):
    return [label for pat, label in RISKY_CSS if re.search(pat, code)]


def check_flag(flag):
    if not isinstance(flag, str) or not FLAG_RE.match(flag):
        return False, "invalid format"
    name, _, value = flag.partition("=")
    if name in BLOCKED_FLAGS:
        return False, "flag blocked for security reasons"
    if name in ("--disable-features", "--enable-features", "--disable-blink-features") and RISKY_FEATURES.search(value):
        return False, "feature switch weakens browser security"
    return True, ""


def _flatten(d, prefix=""):
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            yield from _flatten(v, key + ".")
        else:
            yield key, v


def clean_setting(key, val):
    """Return the cleaned value if valid, otherwise raise ValueError."""
    typ = SETTINGS_WHITELIST[key]
    if not isinstance(val, typ):
        raise ValueError(f"{key}: wrong type")
    if key == "search.url" or key == "search.suggest_url":
        if val == "" and key == "search.suggest_url":
            return val
        u = urlparse(val.replace("{searchTerms}", "x"))
        if u.scheme != "https" or not u.netloc:
            raise ValueError(f"{key}: must be an https URL")
        if key == "search.url" and "{searchTerms}" not in val:
            raise ValueError("search.url must contain {searchTerms}")
    elif key == "homepage":
        if val != "about:blank" and not re.match(r"^https?://", val):
            raise ValueError("homepage must be about:blank or an http(s) URL")
    elif key == "appearance.theme_color":
        if not COLOR_RE.match(val):
            raise ValueError("theme_color must be #rrggbb")
    elif key == "appearance.custom_css":
        if len(val) > 20000:
            raise ValueError("custom_css is too long")
    elif key in ("brand.name", "search.name", "search.keyword"):
        if not re.match(r"^[\w .\-]{1,40}$", val):
            raise ValueError(f"{key}: disallowed characters")
    elif key == "newtab.title":
        if len(val) > 80 or re.search(r"[<>]", val):
            raise ValueError("newtab.title: at most 80 characters, no < or >")
    elif key == "newtab.shortcuts":
        val = ["%s | %s" % parse_shortcut(x) for x in val[:12]]
    elif key in ("site_rules.block", "site_rules.allow"):
        out = []
        for x in val:
            if not isinstance(x, str) or not DOMAIN_RE.match(x.strip()):
                raise ValueError(f"{key}: invalid entry {x!r}")
            out.append(x.strip())
        val = out[:2000]
    return val


def sanitize_patch(patch):
    """settings_patch -> (clean flat dict, list of issues)."""
    ok, issues = {}, []
    if not isinstance(patch, dict):
        return ok, ["settings_patch is not an object"]
    for key, val in _flatten(patch):
        if key not in SETTINGS_WHITELIST:
            issues.append(f"Ignored setting that is not allowed: {key}")
            continue
        try:
            if key == "appearance.custom_css" and isinstance(val, str) and scan_css(val):
                raise ValueError("appearance.custom_css: external resources (@import / url(http...)) are not allowed in AI plans")
            ok[key] = clean_setting(key, val)
        except ValueError as e:
            issues.append(str(e))
    return ok, issues


def sanitize_mod(m):
    """AI/user mod -> (cleaned mod, warnings). Raises ValueError on a malformed mod."""
    if not isinstance(m, dict):
        raise ValueError("Invalid mod format")
    name = str(m.get("name", "")).strip()[:60]
    if not name:
        raise ValueError("Mod has no name")
    matches = m.get("matches") or ["<all_urls>"]
    if not isinstance(matches, list) or not all(isinstance(x, str) and MATCH_RE.match(x) for x in matches):
        raise ValueError("Invalid matches pattern")
    css, js = str(m.get("css", "")), str(m.get("js", ""))
    if len(css) > 50000 or len(js) > 50000:
        raise ValueError("Code is too long")
    run_at = m.get("run_at", "document_idle")
    if run_at not in ("document_start", "document_end", "document_idle"):
        run_at = "document_idle"
    warnings = [f"JS: {w}" for w in scan_js(js)] + [f"CSS: {w}" for w in scan_css(css)]
    if "<all_urls>" in matches and js.strip():
        warnings.append("JS runs on all websites")
    return {
        "name": name,
        "description": str(m.get("description", ""))[:300],
        "matches": matches,
        "css": css,
        "js": js,
        "run_at": run_at,
    }, warnings


def sanitize_plan(plan):
    """Validate a whole AI plan. Returns dict(clean plan + warnings + issues)."""
    if not isinstance(plan, dict):
        raise ValueError("The plan is not a JSON object")
    issues, warnings = [], []
    patch, iss = sanitize_patch(plan.get("settings_patch") or {})
    issues += iss
    flags = []
    raw_flags = plan.get("flags")
    if not isinstance(raw_flags, list):
        if raw_flags:
            issues.append("flags must be a list")
        raw_flags = []
    for f in raw_flags[:50]:
        good, why = check_flag(f)
        if good:
            flags.append(f)
        else:
            issues.append(f"Flag rejected {f!r}: {why}")
    mods = []
    raw_mods = plan.get("mods")
    if not isinstance(raw_mods, list):
        if raw_mods:
            issues.append("mods must be a list")
        raw_mods = []
    for m in raw_mods[:10]:
        try:
            cm, w = sanitize_mod(m)
            mods.append({**cm, "warnings": w})
            warnings += [f"[{cm['name']}] {x}" for x in w]
        except ValueError as e:
            issues.append(f"Mod rejected: {e}")
    recs = []
    raw_recs = plan.get("recommended_extensions")
    for r in (raw_recs if isinstance(raw_recs, list) else [])[:10]:
        if isinstance(r, dict) and r.get("name"):
            recs.append({"name": str(r["name"])[:80], "reason": str(r.get("reason", ""))[:300]})
    return {
        "summary": str(plan.get("summary", ""))[:1000],
        "settings_patch": patch,
        "flags": flags,
        "mods": mods,
        "recommended_extensions": recs,
        "warnings": warnings,
        "issues": issues,
    }
