"""Name/icon branding: apply icon and product name to a copy of chrome.exe using rcedit."""
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

from . import settings

RCEDIT_URL = "https://github.com/electron/rcedit/releases/latest/download/rcedit-x64.exe"


def _safe_name(name):
    return re.sub(r"[^\w\-]", "", name) or "MyBrowser"


def _rcedit():
    f = settings.paths()["cache"] / "rcedit-x64.exe"
    if not f.exists():
        req = urllib.request.Request(RCEDIT_URL, headers={"User-Agent": "ChromiumChanger"})
        with urllib.request.urlopen(req, timeout=60) as r:
            f.write_bytes(r.read())
    return f


def _to_ico(src, dst):
    """png/jpg -> ico (requires Pillow)."""
    from PIL import Image  # pip install pillow
    img = Image.open(src).convert("RGBA")
    img.save(dst, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


def apply(s, exe, log=print):
    """Create a branded exe and return its path. Falls back to the original exe on failure."""
    exe = Path(exe)
    name = _safe_name(s["brand"]["name"])
    target = exe.with_name(f"{name}.exe")
    if sys.platform != "win32":
        log("(not Windows, skipping branding)")
        return exe
    try:
        if target != exe:
            shutil.copy2(exe, target)
        cmd = [str(_rcedit()), str(target),
               "--set-version-string", "ProductName", s["brand"]["name"],
               "--set-version-string", "FileDescription", s["brand"]["name"],
               "--set-version-string", "InternalName", name,
               "--set-version-string", "OriginalFilename", f"{name}.exe",
               "--set-version-string", "CompanyName", s["brand"]["name"]]
        icon = s["brand"].get("icon", "").strip()
        if icon:
            ip = Path(icon)
            if not ip.exists():
                log(f"Icon file not found: {icon}")
            else:
                if ip.suffix.lower() != ".ico":
                    ico = settings.paths()["cache"] / "brand.ico"
                    _to_ico(ip, ico)
                    ip = ico
                cmd += ["--set-icon", str(ip)]
        subprocess.run(cmd, check=True, capture_output=True, timeout=60)
        log(f"Branding applied: {target.name}")
        return target
    except Exception as e:  # network error, Pillow missing, etc.
        log(f"Branding partly failed ({e}). Using the original chrome.exe.")
        return exe


def quote_arg(a):
    """Quote a command-line argument for cmd/shortcut use when it contains spaces."""
    if " " not in a:
        return a
    if a.startswith("--") and "=" in a:
        k, _, v = a.partition("=")
        return f'{k}="{v}"'
    return f'"{a}"'


def _desktop():
    """Real desktop folder (handles OneDrive-redirected desktops)."""
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command",
                            "[Environment]::GetFolderPath('Desktop')"],
                           capture_output=True, text=True, timeout=20)
        p = Path(r.stdout.strip())
        if r.stdout.strip() and p.exists():
            return p
    except Exception:
        pass
    p = Path.home() / "Desktop"
    return p if p.exists() else None


def _start_menu():
    base = os.environ.get("APPDATA")
    return Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs" if base else None


def write_lnk(lnk, exe, args):
    """Create a .lnk (raises on failure)."""
    def q(x):
        return "'" + str(x).replace("'", "''") + "'"
    ps = (f"$s=(New-Object -COM WScript.Shell).CreateShortcut({q(lnk)});"
          f"$s.TargetPath={q(exe)};$s.Arguments={q(' '.join(quote_arg(a) for a in args))};"
          f"$s.WorkingDirectory={q(Path(exe).parent)};$s.IconLocation={q(str(exe) + ',0')};$s.Save()")
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True, capture_output=True, timeout=30)
    return lnk


def make_shortcut(s, exe, args, log=print):
    """Create or remove the browser's Desktop / Start-menu shortcuts according to settings['shortcuts']."""
    if sys.platform != "win32":
        return
    want = s.get("shortcuts", {})
    targets = {"Desktop": (_desktop(), want.get("desktop", True)),
               "Start menu": (_start_menu(), want.get("start_menu", True))}

    def q(x):
        return "'" + str(x).replace("'", "''") + "'"
    for label, (folder, enabled) in targets.items():
        if not folder or not folder.exists():
            if enabled:
                log(f"{label} folder not found; shortcut skipped. Use the launcher .bat in the program folder.")
            continue
        lnk = folder / f"{s['brand']['name']}.lnk"
        if not enabled:
            if lnk.exists():
                try:
                    lnk.unlink()
                    log(f"{label} shortcut removed.")
                except OSError as e:
                    log(f"Could not remove {label} shortcut: {e}")
            continue
        ps = (f"$s=(New-Object -COM WScript.Shell).CreateShortcut({q(lnk)});"
              f"$s.TargetPath={q(exe)};$s.Arguments={q(' '.join(quote_arg(a) for a in args))};"
              f"$s.WorkingDirectory={q(Path(exe).parent)};$s.IconLocation={q(str(exe) + ',0')};$s.Save()")
        try:
            subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True,
                           capture_output=True, timeout=30)
            log(f"{label} shortcut created: {lnk}")
        except Exception as e:
            log(f"{label} shortcut failed: {e}")


def make_launcher_bat(s, exe, args, log=print):
    """Write 'Launch <Brand>.bat' into the program/app-data folder. Always starts the browser WITH the right flags."""
    name = _safe_name(s["brand"]["name"])
    bat = settings.APPDIR / f"Launch {name}.bat"
    bat.parent.mkdir(parents=True, exist_ok=True)
    line = f'start "" "{exe}" ' + " ".join(quote_arg(a) for a in args)
    bat.write_bytes(("@echo off\r\n" + line + "\r\n").encode("utf-8", "replace"))
    log(f"Launcher written: {bat}")
