"""Create, copy, rename, delete and switch profiles."""
import json
import shutil

from . import settings


def list_profiles():
    root = settings.profiles_root()
    return sorted(p.name for p in root.iterdir() if p.is_dir()) if root.exists() else []


def _check_new(name):
    if not settings.valid_profile_name(name):
        raise ValueError("Profile names may contain letters, digits, space, dot, dash, underscore (max 30).")
    if name in list_profiles() or name.lower() in [p.lower() for p in list_profiles()]:
        raise ValueError(f"A profile named '{name}' already exists.")


def create(name, copy_from=None):
    """New profile. With copy_from: copies settings and mods (never browsing data)."""
    _check_new(name)
    root = settings.profiles_root()
    dest = root / name
    dest.mkdir(parents=True)
    if copy_from:
        src = root / copy_from
        if (src / "settings.json").exists():
            shutil.copy2(src / "settings.json", dest / "settings.json")
        if (src / "mods").is_dir():
            shutil.copytree(src / "mods", dest / "mods")
    s = json.loads((dest / "settings.json").read_text(encoding="utf-8")) if (dest / "settings.json").exists() else {}
    # each profile gets its own browser/shortcut name so they do not collide
    brand = dict(s.get("brand", settings.DEFAULTS["brand"]))
    brand["name"] = f"{settings.DEFAULTS['brand']['name']}-{name}".replace(" ", "-")
    s["brand"] = brand
    (dest / "settings.json").write_text(json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")
    return name


def rename(old, new):
    if old == settings.active():
        raise ValueError("Switch to another profile before renaming the active one.")
    _check_new(new)
    (settings.profiles_root() / old).rename(settings.profiles_root() / new)


def delete(name):
    names = list_profiles()
    if name == settings.active():
        raise ValueError("The active profile cannot be deleted. Switch to another profile first.")
    if len(names) <= 1:
        raise ValueError("At least one profile is required.")
    shutil.rmtree(settings.profiles_root() / name)


def switch(name):
    settings.set_active(name)
