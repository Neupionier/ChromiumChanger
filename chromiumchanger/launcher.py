"""Assemble launch arguments, apply everything (build_all), and launch."""
import subprocess
import sys

from . import branding, extbuilder, extsources, fetcher, mods, policies, settings

GOOGLE_FLAGS = [
    "--disable-background-networking", "--disable-sync", "--no-pings",
    "--no-default-browser-check", "--no-first-run", "--disable-breakpad",
    "--disable-domain-reliability", "--disable-client-side-phishing-detection",
    "--disable-default-apps", "--google-api-key=no", "--google-default-client-id=no",
    "--google-default-client-secret=no",
]
GOOGLE_DISABLED_FEATURES = [
    "OptimizationHints", "Translate", "MediaRouter", "InterestFeedContentSuggestions",
    "AutofillServerCommunication", "PrivacySandboxSettings4", "SidePanelPinning",
    "ChromeWhatsNewUI", "NtpModules",
]
FINGERPRINT_FLAGS = [  # ungoogled-chromium only (ignored by plain Chromium)
    "--fingerprinting-canvas-image-data-noise",
    "--fingerprinting-canvas-measuretext-noise",
    "--fingerprinting-client-rects-noise",
]


DEV_FLAGS = {
    "auto_open_devtools": ["--auto-open-devtools-for-tabs"],
    "insecure_localhost": ["--allow-insecure-localhost"],
    "enable_logging": ["--enable-logging", "--v=0"],   # writes chrome_debug.log in the profile folder
    "devtools_experiments": ["--enable-devtools-experiments"],
    "disable_cache": ["--disk-cache-size=1", "--media-cache-size=1"],
}


def _merge_features(flags):
    """Only the last --disable/enable-features flag takes effect, so merge them into one."""
    feats = {"--disable-features": [], "--enable-features": []}
    rest = []
    for f in flags:
        k, _, v = f.partition("=")
        if k in feats:
            feats[k] += [x for x in v.split(",") if x]
        elif f not in rest:
            rest.append(f)
    for k, v in feats.items():
        if v:
            rest.append(f"{k}={','.join(dict.fromkeys(v))}")
    return rest


def build_args(s, ext_dirs, extra=None):
    p = settings.paths()
    flags = [f"--user-data-dir={p['profile']}"]
    flags.append("--load-extension=" + ",".join(str(d) for d in ext_dirs))
    if s["google_removal"]:
        flags += GOOGLE_FLAGS + ["--disable-features=" + ",".join(GOOGLE_DISABLED_FEATURES)]
    if s["privacy"]["fingerprint"]:
        flags += FINGERPRINT_FLAGS
    if s["appearance"]["dark_mode"]:
        flags += ["--force-dark-mode", "--enable-features=WebContentsForceDark"]
    dev = s.get("developer", {})
    for key, extra in DEV_FLAGS.items():
        if dev.get(key):
            flags += extra
    flags += list(extra or [])
    flags += s.get("flags", [])
    return _merge_features(flags)


def build_all(s=None, log=print):
    """Settings -> rebuild extension/theme/policies/branding/shortcut. Returns launch info."""
    s = s or settings.load()
    blocker = extsources.prepare(s, log)
    core = extbuilder.build_core(s, log)
    theme = extbuilder.build_theme(s)
    policies.apply(policies.build(s), log)
    ext_dirs = [core, theme] + ([blocker["path"]] if blocker["path"] else [])
    log(f"Ad blocker: {extsources.LABELS.get(blocker['engine'], 'off')}")
    args = build_args(s, ext_dirs, blocker["flags"])
    exe = fetcher.find_exe()
    if exe:
        exe = branding.apply(s, exe, log)
        branding.make_shortcut(s, exe, args, log)
        branding.make_launcher_bat(s, exe, args, log)
        log('IMPORTANT: start the browser with the desktop shortcut, the generated Launch .bat, or the Launch button. '
            'Opening the .exe directly skips the extensions (ad blocker, theme) and flags.')
    else:
        log("The browser is not installed yet. Run 'Install' first.")
    return {"exe": str(exe) if exe else None, "args": args}


def launch(log=print, url=None):
    """Rebuild everything, then start the browser (optionally opening a URL)."""
    info = build_all(log=log)
    if not info["exe"]:
        raise RuntimeError("The browser is not installed")
    kw = {}
    if sys.platform == "win32":
        kw["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | NEW_PROCESS_GROUP
    args = [*info["args"]] + ([url] if url else [])
    if sys.platform == "win32" and policies.is_admin():
        # The app runs as administrator (needed for policies); start the browser WITHOUT elevation through
        # Explorer so it keeps its sandbox and normal permissions.
        lnk = branding.write_lnk(settings.APPDIR / ".launch.lnk", info["exe"], args)
        subprocess.Popen(["explorer.exe", str(lnk)])
    else:
        subprocess.Popen([info["exe"], *args], close_fds=True, **kw)
    log("Browser launched.")
