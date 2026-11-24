"""AI provider connections (Ollama / OpenAI-compatible / Anthropic) and customization-plan generation."""
import json
import os
import re
import urllib.request

from . import settings, validate

SYSTEM = """You are the customization planner of "ChromiumChanger", a tool that customizes a Chromium browser.
The user describes what they want. Reply with ONE JSON object only (no prose, no markdown fences) with this shape:
{
 "summary": "short explanation, in the SAME LANGUAGE as the user's request",
 "settings_patch": { ... only keys from the allowed list below ... },
 "flags": ["--chromium-command-line-flag", ...],
 "mods": [ {"name": "...", "description": "...", "matches": ["https://*.example.com/*"], "css": "...", "js": "...", "run_at": "document_idle"} ],
 "recommended_extensions": [ {"name": "...", "reason": "..."} ]
}
Allowed settings_patch keys (nested JSON): brand.name, search.{name,keyword,url,suggest_url} (url must be https and contain {searchTerms}),
homepage, adblock.enabled, privacy.{fingerprint,webrtc_protect,block_third_party_cookies,do_not_track},
appearance.{dark_mode,theme_color "#rrggbb",custom_css}, site_rules.{block[],allow[]} (URL patterns like "example.com" or "*.example.com"),
newtab.{enabled,title,search,clock,clock_24h,shortcuts[]} (the browser's own New Tab page: search box, clock, shortcut tiles; shortcuts are strings "Name | https://address", max 12).
Rules:
- Prefer the simplest mechanism: settings_patch > flags > CSS-only mod > JS mod.
- Mods are content scripts (CSS/JS injected into pages). Keep `matches` as narrow as the request allows.
- Never write code that sends data to external servers, reads passwords/cookies, or loads remote scripts.
- Never use dangerous flags (--no-sandbox, --disable-web-security, proxies, remote debugging, etc.).
- Omit keys you do not need. If the request cannot be done safely, return an empty plan and explain in summary.
- Change ONLY what the request asks for. Never touch unrelated settings (for example do not enable dark mode or change colors unless asked).
- `matches` must be a valid match pattern: "<all_urls>" or like "https://*/*" or "https://*.example.com/*" (scheme://host/path). Never use chrome:// or about: URLs.
- Requests about the first page / start page / new tab (search bar, clock, shortcuts) are done with settings_patch newtab.* (set newtab.enabled to true), NEVER with mods.
Examples:
Request: "make Wikipedia dark" -> {"summary":"Dark background for Wikipedia.","mods":[{"name":"Wikipedia dark","matches":["https://*.wikipedia.org/*"],"css":"body{background:#111!important;color:#ddd!important}"}]}
Request: "new tab with a clock and a search bar" -> {"summary":"New tab page with search box and clock.","settings_patch":{"newtab":{"enabled":true,"search":true,"clock":true}}}
Request: "use Brave search" -> {"summary":"Brave Search as the default.","settings_patch":{"search":{"name":"Brave","keyword":"brave","url":"https://search.brave.com/search?q={searchTerms}"}}}
"""


def _post(url, body, headers, timeout=180):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


PROVIDER_DEFAULTS = {
    "ollama": {"base_url": "http://localhost:11434", "model": ""},
    "openai": {"base_url": "https://api.openai.com/v1", "model": ""},
    "anthropic": {"base_url": "https://api.anthropic.com", "model": ""},
}


class AIDisabled(Exception):
    pass


def chat(cfg, system, user, json_mode=True):
    prov, model = cfg.get("provider", "none"), cfg.get("model", "")
    if prov in ("", "none"):
        raise AIDisabled("AI is turned off. Choose a provider (local Ollama or an API) in the AI tab first.")
    if not model:
        raise AIDisabled("Enter a model name in the AI settings first.")
    base = (cfg.get("base_url") or PROVIDER_DEFAULTS.get(prov, {}).get("base_url", "")).rstrip("/")
    key = cfg.get("api_key") or os.environ.get("CC_API_KEY", "")
    if prov == "ollama":
        if base.startswith(("http://localhost", "http://127.0.0.1")):
            from . import localai
            if not localai.running() and localai.find_exe():
                localai.start()
        r = _post(f"{base}/api/chat", {
            "model": model, "stream": False, "options": {"temperature": 0.2},
            **({"format": "json"} if json_mode else {}),
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}, {})
        return r["message"]["content"]
    if prov == "openai":  # OpenAI, xAI (Grok), LM Studio, OpenRouter and other compatible APIs
        h = {"Authorization": f"Bearer {key}"} if key else {}
        r = _post(f"{base}/chat/completions", {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}, h)
        return r["choices"][0]["message"]["content"]
    if prov == "anthropic":
        r = _post(f"{base}/v1/messages", {
            "model": model, "max_tokens": 8000, "system": system,
            "messages": [{"role": "user", "content": user}]},
            {"x-api-key": key, "anthropic-version": "2023-06-01"})
        return "".join(b.get("text", "") for b in r["content"])
    raise ValueError(f"Unknown provider: {prov}")


def extract_json(text):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    i, j = text.find("{"), text.rfind("}")
    if i < 0 or j < i:
        raise ValueError("No JSON found in the AI response")
    return json.loads(text[i:j + 1])


def test(cfg):
    """Tiny round trip to check the connection. Returns the model reply."""
    return chat(cfg, "Reply with the single word OK.", "ping", json_mode=False)[:200]


def plan(settings_obj, request):
    """User request -> validated plan. Does not apply anything."""
    ctx = {k: settings_obj[k] for k in ("brand", "search", "homepage", "privacy", "appearance", "newtab")}
    user = f"Current settings:\n{json.dumps(ctx, ensure_ascii=False)}\n\nUser request:\n{request}"
    raw = chat(settings.load_ai(), SYSTEM, user)
    return validate.sanitize_plan(extract_json(raw))
