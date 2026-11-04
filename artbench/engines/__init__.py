"""Engine adapters by name; a project picks one with config "engine" (default "unity", case and spaces ignored). The
calls every module uses for the engine side: dump(), unreachable() and content_root()."""
import os

from ..errors import Unavailable
from .unity import UnityAdapter

ADAPTERS = {"unity": UnityAdapter()}


def of(cfg):
    """The adapter for this project's engine; Unavailable when the config names an engine Artbench does not support."""
    raw = (cfg or {}).get("engine") or "unity"
    adapter = ADAPTERS.get(raw.strip().lower()) if isinstance(raw, str) else None
    if adapter is None:
        raise Unavailable(f"engine not supported: {raw!r} (supported: {', '.join(sorted(ADAPTERS))})")
    return adapter


def dump(cfg, force=False):
    """The engine asset dump for this project, rebuilt when missing, stale or forced. None without an engine root."""
    return of(cfg).build_dump(cfg, force)


def unreachable(cfg):
    """True when the config names an engine folder that cannot be read now (unplugged drive, moved clone): sync is
    then unknown, never "missing", and nothing may be sent or pulled."""
    root = cfg.get("engine_root")
    return bool(root) and not os.path.isdir(root)


def content_root(cfg):
    """The engine's content root (Unity: the Assets folder)."""
    return of(cfg).content_root(cfg)
