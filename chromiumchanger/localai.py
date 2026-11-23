"""One-click local AI: download a portable Ollama, start it, and pull a model.

Ollama is fetched from its official GitHub release (SHA-256 verified) and unpacked into
<workspace>/ollama/bin; models are stored in <workspace>/ollama/models. Nothing is installed
system-wide and no administrator rights are needed. An Ollama already installed on this PC is reused.
"""
import atexit
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from . import extsources, settings

BASE = "http://127.0.0.1:11434"
REPO = "ollama/ollama"
MODELS = [
    ("qwen2.5-coder:3b", "Small and fast (~2 GB download, 8 GB RAM)"),
    ("qwen2.5-coder:7b", "Balanced, recommended (~4.7 GB download, 16 GB RAM)"),
    ("qwen2.5-coder:14b", "Best quality (~9 GB download, 16 GB+ RAM or a GPU)"),
]
_proc = None


def root():
    d = settings.WORK / "ollama"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _portable_exe():
    return root() / "bin" / ("ollama.exe" if sys.platform == "win32" else "ollama")


def find_exe():
    """Path of an usable ollama executable, or None."""
    p = _portable_exe()
    if p.is_file():
        return str(p)
    found = shutil.which("ollama")
    if found:
        return found
    local = os.environ.get("LOCALAPPDATA")
    if local:
        c = Path(local) / "Programs" / "Ollama" / "ollama.exe"
        if c.is_file():
            return str(c)
    return None


def _get(path, timeout=3):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def running():
    try:
        _get("/api/version")
        return True
    except Exception:
        return False


def list_models():
    try:
        return [m["name"] for m in _get("/api/tags").get("models", [])]
    except Exception:
        return []


def status():
    exe = find_exe()
    if not exe:
        return "Not installed"
    return "Running" if running() else "Installed (stopped)"


def start(log=print):
    global _proc
    if running():
        return
    exe = find_exe()
    if not exe:
        raise RuntimeError("Ollama is not installed. Use 'Install local AI' first.")
    env = dict(os.environ)
    if Path(exe) == _portable_exe():
        env["OLLAMA_MODELS"] = str(root() / "models")
    flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
    log("Starting the local AI engine...")
    _proc = subprocess.Popen([exe, "serve"], env=env, creationflags=flags,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
    for _ in range(60):
        if running():
            return
        if _proc.poll() is not None:
            break
        time.sleep(0.5)
    raise RuntimeError("The local AI engine did not start.")


def stop():
    global _proc
    if _proc and _proc.poll() is None:
        _proc.terminate()
    _proc = None


atexit.register(stop)


def _asset_name():
    arm = platform.machine().lower() in ("arm64", "aarch64")
    return "ollama-windows-arm64.zip" if arm else "ollama-windows-amd64.zip"


def install_runtime(log=print):
    if sys.platform != "win32":
        raise RuntimeError("One-click install is available on Windows. Install Ollama from ollama.com instead.")
    log("Looking up the latest Ollama release...")
    with extsources._open(f"https://api.github.com/repos/{REPO}/releases?per_page=5") as r:
        releases = json.loads(r.read().decode())
    want = _asset_name()
    asset = tag = None
    for rel in releases:
        if rel.get("prerelease") or rel.get("draft"):
            continue
        for a in rel.get("assets", []):
            if a["name"] == want:
                asset, tag = a, rel["tag_name"]
                break
        if asset:
            break
    if not asset:
        raise RuntimeError("No Ollama download found for this PC.")
    size = asset["size"]
    log(f"Downloading Ollama {tag} ({size // 1048576} MB). This can take a while...")
    zpath = settings.paths()["cache"] / asset["name"]
    h = hashlib.sha256()
    done = 0
    last = -10
    with extsources._open(asset["browser_download_url"]) as r, open(zpath, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            h.update(chunk)
            done += len(chunk)
            pct = done * 100 // max(size, 1)
            if pct >= last + 10:
                last = pct
                log(f"  {pct}%")
    digest = (asset.get("digest") or "").removeprefix("sha256:")
    if digest and digest.lower() != h.hexdigest():
        zpath.unlink()
        raise RuntimeError("SHA-256 checksum mismatch. The download was discarded.")
    log("Checksum verified. Unpacking...")
    dest = root() / "bin"
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    extsources._extract(zpath, dest)
    try:
        zpath.unlink()
    except OSError:
        pass
    if not _portable_exe().is_file():
        raise RuntimeError("ollama.exe was not found in the download.")
    log("Ollama is ready.")


def pull(model, log=print):
    log(f"Downloading model {model}...")
    req = urllib.request.Request(BASE + "/api/pull", data=json.dumps({"model": model, "stream": True}).encode(),
                                 method="POST", headers={"Content-Type": "application/json"})
    last, last_status = -10, ""
    with urllib.request.urlopen(req, timeout=600) as r:
        for line in r:
            if not line.strip():
                continue
            d = json.loads(line.decode("utf-8"))
            if d.get("error"):
                raise RuntimeError(d["error"])
            st = d.get("status", "")
            if d.get("total"):
                pct = d.get("completed", 0) * 100 // d["total"]
                if pct >= last + 10:
                    last = pct
                    log(f"  {pct}%")
            elif st != last_status:
                last_status = st
                log("  " + st)
                last = -10


def setup(model, log=print):
    """Install (if needed), start, download the model and switch the AI settings to it."""
    if not find_exe():
        install_runtime(log)
    start(log)
    if model not in list_models():
        pull(model, log)
    else:
        log(f"Model {model} is already downloaded.")
    cfg = settings.load_ai()
    cfg.update(provider="ollama", model=model, base_url=BASE)
    settings.save_ai(cfg)
    log("Local AI is ready and selected as the AI provider.")
    return model
