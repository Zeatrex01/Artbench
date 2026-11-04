"""Engine-side layout rules: where each kind of art asset is expected to live under the engine root. Off until it is
turned on (layout_enabled; a project that wrote its own layout_rules is on). Turning it on learns the rules from the
project: for each kind, the folders holding most of its assets are allowed, so what sits elsewhere is flagged. The
check is advisory, nothing is moved."""
import fnmatch
import os

from . import config, engines, store

LEARN_KINDS = ("model", "texture", "material", "prefab")
LEARN_SHARE = 0.15                   # a folder holding at least this share of a kind (and two of them) is where it lives
DEFAULT_IGNORE = ["TechArt/Samples/", "Editor/", "Resources/"]


def _folder(rel):
    d = os.path.dirname(rel).replace("\\", "/")
    return (d + "/") if d else ""


def _matches(folder, patterns):
    for p in patterns:
        p = p.replace("\\", "/")
        if p.endswith("*"):
            if fnmatch.fnmatch(folder, p) or fnmatch.fnmatch(folder, p + "/") or folder.startswith(p[:-1]):
                return True
        elif fnmatch.fnmatch(folder, p):
            return True
    return False


def enabled(cfg):
    return bool(cfg.get("layout_enabled", bool(cfg.get("layout_rules"))))


def _assets(cfg, dump):
    """(asset, path relative to the engine root) for every dump asset under it and outside the ignored folders."""
    aroot = dump["assets_root"]
    rel_root = os.path.relpath(cfg["engine_root"], aroot).replace("\\", "/").rstrip("/")
    eroot = "" if rel_root == "." else rel_root + "/"          # project mode: the engine root is the content root
    ignore = tuple(cfg.get("layout_ignore", DEFAULT_IGNORE))
    for a in dump["assets"].values():
        if a["path"].startswith(eroot) and not a["path"][len(eroot):].startswith(ignore):
            yield a, a["path"][len(eroot):]


def learn(cfg, dump):
    """Rules from where the assets are now: per kind, the two-level folders (Art/Props/) holding at least LEARN_SHARE
    of that kind and two of its assets. Never the root."""
    if not dump:
        return []
    counts = {}
    for a, rel in _assets(cfg, dump):
        if a["kind"] in LEARN_KINDS:
            parts = [p for p in _folder(rel).split("/") if p]
            if parts:
                key = "/".join(parts[:2]) + "/"
                counts.setdefault(a["kind"], {}).setdefault(key, 0)
                counts[a["kind"]][key] += 1
    rules = []
    for kind in LEARN_KINDS:
        total = sum(counts.get(kind, {}).values())
        allow = sorted(f + "*" for f, n in counts.get(kind, {}).items() if n >= 2 and n / total >= LEARN_SHARE)
        if allow:
            rules.append({"kinds": [kind], "allow": allow,
                          "hint": f"Learned from the project: {kind}s live in " + ", ".join(a[:-1] for a in allow)})
    return rules


def status(cfg, dump):
    """{"enabled", "rules" (the project's own), "proposed" (learned, what turning on would write when it has none)}."""
    own = cfg.get("layout_rules") or []
    return {"enabled": enabled(cfg), "rules": own, "proposed": [] if own else learn(cfg, dump)}


def settings(cfg, dump, enable=None, allow_kind=None, allow_folder=None):
    """Turns layout on (writing the learned rules when the project has none) or off (keeping them), and accepts a
    folder for a kind (allow_folder "" is the engine root). Each change is a LAYOUT history line. Returns status()."""
    raw = store._read_json(cfg["config_path"], {})
    raw = raw if isinstance(raw, dict) else {}
    if enable and not raw.get("layout_rules"):
        raw["layout_rules"] = learn(cfg, dump)
    if enable is not None:
        raw["layout_enabled"] = bool(enable)
        store.log(cfg, "LAYOUT", "on" if enable else "off")
    if allow_kind:
        folder = (allow_folder or "").replace("\\", "/").strip("/")
        if ".." in folder.split("/"):
            raise ValueError(f"not a folder: {allow_folder!r}")
        pattern = folder + "/*" if folder else ""
        rules = raw.setdefault("layout_rules", [])
        rule = next((r for r in rules if allow_kind in r.get("kinds", [])), None)
        if rule is None:
            rules.append({"kinds": [allow_kind], "allow": [pattern], "hint": ""})
        elif pattern not in rule["allow"]:
            rule["allow"].append(pattern)
        store.log(cfg, "LAYOUT", "allow", allow_kind, folder or "(root)")
    store._write_json(cfg["config_path"], raw)
    return status(config.load(cfg["config_path"]), dump)


def check(cfg, dump):
    """[{path, kind, folder, hint}] for art assets under the engine root that sit outside their allowed folders."""
    if not dump or not enabled(cfg):
        return []
    if config.is_project_mode(cfg) and not cfg.get("layout_rules"):
        # The default rules are written for an engine art root (Assets/_GAME/<Game>/); against a whole Assets folder
        # they would flag nearly everything. Project mode judges layout only by its own (or learned) rules.
        return []
    rules = cfg.get("layout_rules") or engines.of(cfg).layout_defaults
    aroot = dump["assets_root"]
    issues = []
    for a, rel in _assets(cfg, dump):
        path = a["path"]
        rule = next((r for r in rules if a["kind"] in r["kinds"]), None)
        if not rule:
            continue
        folder = _folder(rel)
        if not _matches(folder, rule["allow"]):
            issues.append({"path": rel, "kind": a["kind"], "folder": folder or "(root)", "hint": rule.get("hint", ""),
                           "engine_path": os.path.normpath(os.path.join(aroot, path))})
    issues.sort(key=lambda i: (i["kind"], i["path"]))
    return issues
