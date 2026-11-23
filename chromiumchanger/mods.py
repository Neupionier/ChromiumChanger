"""Store for AI/user-made 'mods' (CSS/JS content scripts) plus change history (rollback)."""
import json
import re
import time
import uuid

from . import settings


def _dir():
    return settings.paths()["mods"]


def list_mods():
    out = []
    for f in sorted(_dir().glob("*.json")):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            pass
    return out


def save_mod(m):
    mid = m.get("id") or uuid.uuid4().hex[:10]
    if not re.match(r"^[a-f0-9]{10}$", mid):
        raise ValueError("Invalid mod id")
    m = {**m, "id": mid, "enabled": m.get("enabled", True)}
    m.pop("warnings", None)
    (_dir() / f"{mid}.json").write_text(json.dumps(m, indent=2, ensure_ascii=False), encoding="utf-8")
    return m


def delete_mod(mid):
    if not re.match(r"^[a-f0-9]{10}$", mid):
        raise ValueError("Invalid mod id")
    f = _dir() / f"{mid}.json"
    if f.exists():
        f.unlink()


def toggle_mod(mid, enabled):
    f = _dir() / f"{mid}.json"
    m = json.loads(f.read_text(encoding="utf-8"))
    m["enabled"] = bool(enabled)
    save_mod(m)


# ---- history / rollback ----

def snapshot(label):
    h = settings.paths()["history"]
    sid = time.strftime("%Y%m%d-%H%M%S")
    data = {"id": sid, "label": label, "settings": settings.load(), "mods": list_mods()}
    (h / f"{sid}.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return sid


def list_history():
    h = settings.paths()["history"]
    out = []
    for f in sorted(h.glob("*.json"), reverse=True)[:50]:
        d = json.loads(f.read_text(encoding="utf-8"))
        out.append({"id": d["id"], "label": d["label"], "mods": len(d["mods"])})
    return out


def rollback(sid):
    if not re.match(r"^\d{8}-\d{6}$", sid):
        raise ValueError("Invalid id")
    d = json.loads((settings.paths()["history"] / f"{sid}.json").read_text(encoding="utf-8"))
    settings.save(d["settings"])
    for m in list_mods():
        delete_mod(m["id"])
    for m in d["mods"]:
        save_mod(m)
