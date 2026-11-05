"""Checks on the art of a game project, advisory: nothing is changed. Duplicates are files with the same content in
several places (grouped by size first, then by content hash, so only likely copies are read). Standards are the
project's rules (config `standards` over DEFAULTS): a texture imported larger than texture_max, a texture side that is
not a power of two, Read/Write enabled (a second copy in memory), an uncompressed texture, a name without its kind's
prefix (naming, off by default), a model over the triangle budget (tris_max, off by default; needs Blender's count).
The import settings come from the engine adapter (Unity: the .meta), read only."""
import os

from . import config, engines, files, store

DEFAULTS = {"texture_max": 4096, "power_of_two": True, "read_write": True, "uncompressed": True,
            "naming": False, "prefixes": {"texture": "T_", "material": "M_", "prefab": "PF_", "model": "SM_"},
            "tris_max": None}
RULES = ("texture_max", "power_of_two", "read_write", "uncompressed", "naming", "tris_max")
LEVEL = {"texture_max": "warn", "read_write": "warn", "uncompressed": "warn", "tris_max": "warn",
         "power_of_two": "info", "naming": "info"}
DUPLICATE_KINDS = ("model", "texture", "audio", "material")


def rules(cfg):
    out = dict(DEFAULTS)
    out.update({k: v for k, v in (cfg.get("standards") or {}).items() if k in DEFAULTS})
    return out


def set_rules(cfg, **changes):
    """Writes the given rules into the project config (None leaves one as it is); a STANDARDS history line."""
    unknown = set(changes) - set(DEFAULTS)
    if unknown:
        raise ValueError(f"unknown rule: {', '.join(sorted(unknown))}")
    raw = store._read_json(cfg["config_path"], {})
    raw = raw if isinstance(raw, dict) else {}
    current = raw.setdefault("standards", {})
    for key, value in changes.items():
        if value is None:
            continue
        if key in ("texture_max", "tris_max") and value not in (0, ""):
            value = int(value)
        current[key] = value or None if key in ("texture_max", "tris_max") else value
    store._write_json(cfg["config_path"], raw)
    with store.locked(cfg):
        store.log(cfg, "STANDARDS", ", ".join(f"{k}={v}" for k, v in sorted(changes.items()) if v is not None))
    return rules(config.load(cfg["config_path"]))


def _abs(cfg, path):
    adapter = engines.of(cfg)
    return os.path.join(engines.content_root(cfg), *path[len(adapter.prefix):].split("/"))


def duplicates(cfg, assets):
    """[{sha, size, wasted, assets: [{id, path, kind, usage, used_by_count}]}], the most wasted bytes first."""
    by_size = {}
    for a in assets:
        if a["kind"] in DUPLICATE_KINDS and a.get("size"):
            by_size.setdefault(a["size"], []).append(a)
    groups = {}
    for size, same in by_size.items():
        if len(same) < 2:
            continue
        for a in same:
            try:
                digest = files.sha(_abs(cfg, a["path"]))
            except OSError:
                continue
            groups.setdefault(digest, []).append(a)
    files.save_cache()
    out = []
    for digest, copies in groups.items():
        if len(copies) < 2:
            continue
        size = copies[0]["size"]
        out.append({"sha": digest, "size": size, "wasted": size * (len(copies) - 1),
                    "assets": [{"id": a["id"], "path": a["path"], "kind": a["kind"], "usage": a["usage"],
                                "used_by_count": a.get("used_by_count", len(a.get("used_by") or []))}
                               for a in sorted(copies, key=lambda a: a["path"].lower())]})
    return sorted(out, key=lambda g: (-g["wasted"], g["assets"][0]["path"].lower()))


def _power_of_two(n):
    return n > 0 and n & (n - 1) == 0


def standards(cfg, assets):
    """[{id, path, kind, rule, detail, level}] in rule order, then path."""
    r, adapter, out = rules(cfg), engines.of(cfg), []

    def flag(a, rule, detail):
        out.append({"id": a["id"], "path": a["path"], "kind": a["kind"], "rule": rule, "detail": detail, "level": LEVEL[rule]})
    for a in assets:
        kind = a["kind"]
        if kind not in ("texture", "model", "material", "prefab"):
            continue
        settings = adapter.import_settings(_abs(cfg, a["path"])) if kind in ("texture", "model") else {}
        if kind == "texture":
            image = a.get("image") or {}
            w, h = image.get("width"), image.get("height")
            if w and h:
                side = max(w, h)
                imported = min(side, settings["max_size"]) if settings.get("max_size") else side
                if r["texture_max"] and imported > r["texture_max"]:
                    flag(a, "texture_max", f"imported at {imported} px, the limit is {r['texture_max']}")
                if r["power_of_two"] and not (_power_of_two(w) and _power_of_two(h)):
                    flag(a, "power_of_two", f"{w} x {h}")
            if r["uncompressed"] and settings.get("compressed") is False:
                flag(a, "uncompressed", "compression is off")
        if r["read_write"] and settings.get("readable"):
            flag(a, "read_write", "Read/Write is on: a second copy stays in memory")
        prefix = (r["prefixes"] or {}).get(kind)
        if r["naming"] and prefix and not a["name"].startswith(prefix):
            flag(a, "naming", f"{kind} names start with {prefix}")
        tris = (a.get("stats") or {}).get("tris")
        if kind == "model" and r["tris_max"] and tris and tris > r["tris_max"]:
            flag(a, "tris_max", f"{tris} triangles, the budget is {r['tris_max']}")
    order = {k: i for i, k in enumerate(RULES)}
    return sorted(out, key=lambda i: (order[i["rule"]], i["path"].lower()))


def counts(issues):
    return {rule: sum(1 for i in issues if i["rule"] == rule) for rule in RULES}
