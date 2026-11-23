"""Build/apply Chromium policies (registry Software\\Policies\\Chromium).

Administrator rights are recommended (HKLM); applied policies can be viewed at chrome://policy.
(Once policies are applied, the browser menu may show 'Managed by your organization'.)
"""
import json
import sys

from . import settings

REG_PATH = r"Software\Policies\Chromium"

GOOGLE_OFF = {
    "SyncDisabled": 1,
    "BrowserSignin": 0,
    "MetricsReportingEnabled": 0,
    "SafeBrowsingProtectionLevel": 0,
    "SafeBrowsingExtendedReportingEnabled": 0,
    "TranslateEnabled": 0,
    "SearchSuggestEnabled": 0,
    "UrlKeyedAnonymizedDataCollectionEnabled": 0,
    "BackgroundModeEnabled": 0,
    "PromotionalTabsEnabled": 0,
    "ShoppingListEnabled": 0,
    "SpellCheckServiceEnabled": 0,
    "AlternateErrorPagesEnabled": 0,
    "PrivacySandboxPromptEnabled": 0,
    "PrivacySandboxAdMeasurementEnabled": 0,
    "PrivacySandboxAdTopicsEnabled": 0,
    "PrivacySandboxSiteEnabledAdsEnabled": 0,
    "DefaultBrowserSettingEnabled": 0,
    "ChromeVariations": 2,
    "MediaRouterEnabled": 0,
    "GoogleSearchSidePanelEnabled": 0,
}


def build(s):
    p = {}
    if s["google_removal"]:
        p.update(GOOGLE_OFF)
    # Always force a default search engine so the browser never ends up with "No search".
    se = dict(s["search"])
    if "{searchTerms}" not in (se.get("url") or ""):
        se = {"name": "DuckDuckGo", "keyword": "ddg", "url": "https://duckduckgo.com/?q={searchTerms}",
              "suggest_url": "https://duckduckgo.com/ac/?q={searchTerms}&type=list"}
    p.update({
        "DefaultSearchProviderEnabled": 1,
        "DefaultSearchProviderName": se.get("name") or "Search",
        "DefaultSearchProviderKeyword": se.get("keyword") or "search",
        "DefaultSearchProviderSearchURL": se["url"],
    })
    if se.get("suggest_url"):
        p["DefaultSearchProviderSuggestURL"] = se["suggest_url"]
        p["SearchSuggestEnabled"] = 1
    hp = s["homepage"]
    if hp and hp != "about:blank":
        p["HomepageLocation"] = hp
        p["HomepageIsNewTabPage"] = 0
        p["NewTabPageLocation"] = hp
    pr = s["privacy"]
    if pr.get("block_third_party_cookies"):
        p["BlockThirdPartyCookies"] = 1
    if pr.get("webrtc_protect"):
        p["WebRtcIPHandling"] = "disable_non_proxied_udp"
    if pr.get("do_not_track"):
        p["EnableDoNotTrack"] = 1
    if s["site_rules"]["block"]:
        p["URLBlocklist"] = list(s["site_rules"]["block"])
    if s["site_rules"]["allow"]:
        p["URLAllowlist"] = list(s["site_rules"]["allow"])
    return p


def _delete_tree(winreg, root, path):
    try:
        key = winreg.OpenKey(root, path, 0, winreg.KEY_ALL_ACCESS)
    except FileNotFoundError:
        return
    while True:
        try:
            sub = winreg.EnumKey(key, 0)
        except OSError:
            break
        _delete_tree(winreg, root, path + "\\" + sub)
    winreg.CloseKey(key)
    winreg.DeleteKey(root, path)


def is_admin():
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _count(winreg, root):
    try:
        key = winreg.OpenKey(root, REG_PATH, 0, winreg.KEY_READ)
    except OSError:
        return 0
    n = winreg.QueryInfoKey(key)[1]
    winreg.CloseKey(key)
    return n


def _write(winreg, root, policies):
    _delete_tree(winreg, root, REG_PATH)
    key = winreg.CreateKeyEx(root, REG_PATH, 0, winreg.KEY_ALL_ACCESS)
    for name, val in policies.items():
        if isinstance(val, list):
            sub = winreg.CreateKeyEx(key, name, 0, winreg.KEY_ALL_ACCESS)
            for i, item in enumerate(val, 1):
                winreg.SetValueEx(sub, str(i), 0, winreg.REG_SZ, str(item))
            winreg.CloseKey(sub)
        elif isinstance(val, str):
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, val)
        else:
            winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, int(val))
    winreg.CloseKey(key)


def apply(policies, log=print):
    """Write policies to the registry (HKLM when running as administrator, else HKCU).

    Windows often blocks non-admin writes under HKCU\\Software\\Policies. If every attempt
    fails we do NOT abort: Google removal still works through launch flags, only the
    policy-only features (default search engine, homepage, site rules, ...) are skipped.
    Returns True if the policies were applied.
    """
    out = settings.paths()["work"] / "policies.json"
    out.write_text(json.dumps(policies, indent=2, ensure_ascii=False), encoding="utf-8")
    if sys.platform != "win32":
        log(f"(not Windows, registry step skipped) {out}")
        return False
    import winreg
    targets = []
    if is_admin():
        targets.append((winreg.HKEY_LOCAL_MACHINE, "HKLM"))
    targets.append((winreg.HKEY_CURRENT_USER, "HKCU"))
    ok = False
    for root, name in targets:  # Chromium reads both; write every location we are allowed to
        try:
            _write(winreg, root, policies)
            n = _count(winreg, root)
            log(f"Applied {len(policies)} policies to {name}\\{REG_PATH} (read back: {n} values).")
            ok = True
        except OSError as e:
            log(f"Could not write policies to {name}: {e}")
    if ok:
        log("Policies are read when the browser starts: close ALL browser windows, then start it again "
            "(check chrome://policy).")
        return True
    log("WARNING: policies were NOT applied (registry write was denied). "
        "Launch flags still work, but policy-only settings (default search engine, homepage, "
        "site block/allow lists, WebRTC/cookie/DNT policies) are inactive. "
        "To enable them, close this program and start run.bat with 'Run as administrator'.")
    return False


def remove(log=print):
    if sys.platform == "win32":
        import winreg
        for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                _delete_tree(winreg, root, REG_PATH)
            except OSError as e:
                log(f"Could not clean one registry location: {e}")
        log("Registry policies removed.")
