"""Two-way sync between the art root and the engine root. The bridge's one promise: no file is silently overwritten
on either side. Each model's state is derived from three content hashes: the last state both sides agreed on (the
base, kept in sync_base.json), the art copy and the engine copy. A side that differs from the base has new work; when
both do, the model is in `conflict` and neither direction runs without an explicit force. This module owns the rule,
the base record, the archive paths and the engine -> art direction (pull); deploy.py owns art -> engine (send)."""
import os
import shutil
import time

from . import asset_meta, changes, engines, store
from .errors import NeedsForce, OutsideRoot, Unavailable  # noqa: F401  (re-exported for callers)


def status(base, art_hash, engine_hash, art_mtime, engine_mtime):
    """(sync, basis). sync: same | desktop_newer | engine_newer | conflict. basis: "base" when the recorded base
    decided it, "mtime" when no base is known and the modification times had to."""
    if art_hash == engine_hash:
        return "same", "base"
    if base:
        art_changed = art_hash != base.get("art")
        engine_changed = engine_hash != base.get("engine")
        if art_changed and engine_changed:
            return "conflict", "base"
        return ("desktop_newer" if art_changed else "engine_newer"), "base"
    return ("desktop_newer" if art_mtime > engine_mtime else "engine_newer"), "mtime"


def record_base(cfg, item_id, art_hash, engine_hash):
    """Both sides now agree on this content."""
    with store.locked(cfg):
        base = store.sync_base(cfg)
        base[item_id] = {"art": art_hash, "engine": engine_hash, "time": time.strftime("%Y-%m-%d %H:%M:%S")}
        store.save_sync_base(cfg, base)


def carry_base(cfg, old_id, new_id):
    """The base follows a model that moved between state folders."""
    with store.locked(cfg):
        base = store.sync_base(cfg)
        if old_id in base:
            base[new_id] = base.pop(old_id)
            store.save_sync_base(cfg, base)


def archive_path(cfg, side, root, path):
    """Where a copy of `path` (under `root`, on `side` = art | engine) goes before it is overwritten. Never an
    existing file: a second transfer on the same day gets a time suffix, so no archived copy is ever lost."""
    rel = os.path.relpath(path, root)
    candidate = os.path.normpath(os.path.join(cfg["state_dirs"]["archive"], time.strftime("%Y-%m-%d"), side, rel))
    if not os.path.exists(candidate):
        return candidate
    stem, ext = os.path.splitext(candidate)
    stamp = time.strftime("%H%M%S")
    n = 0
    while True:
        suffixed = f"{stem}.{stamp}{'' if n == 0 else '-' + str(n)}{ext}"
        if not os.path.exists(suffixed):
            return suffixed
        n += 1


def force_reason(basis, overwritten_hash, base_hash):
    """Why a transfer would need force: "no_base" (no sync record yet), "changed" (the side to be overwritten
    differs from the last agreed state) or None."""
    if basis != "base":
        return "no_base"
    if overwritten_hash != base_hash:
        return "changed"
    return None


FORCE_MESSAGES = {
    "no_base": "no sync record for this model yet; force to overwrite (the old copy is archived)",
    "changed": "{side} copy changed since the last sync; force to overwrite (the old copy is archived)",
}


def force_error(reason, side):
    return NeedsForce(FORCE_MESSAGES[reason].format(side=side))


def write_over(source, target):
    """Copies `source` over `target` without ever leaving `target` half-written: the copy goes to a temp file beside
    the target and is swapped in with one rename."""
    tmp = f"{target}.artbench.tmp"
    try:
        shutil.copy2(source, tmp)
        store.replace_with_retry(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def engine_note_ok(cfg, name, path):
    """An engine_path note is honoured only when it names an existing file inside the engine root with the item's
    own file name (compared case-insensitively, as same-name engine copies are found): never another file a send
    would then overwrite."""
    root = cfg.get("engine_root")
    return bool(path and root and inside(path, root) and os.path.isfile(path)
                and os.path.basename(path).lower() == name.lower())


def inside(path, root):
    """True when `path` resolves to a location under `root`."""
    path = os.path.normcase(os.path.abspath(path))
    root = os.path.normcase(os.path.abspath(root))
    try:
        return os.path.commonpath([path, root]) == root
    except ValueError:                      # different drives on Windows
        return False


def refresh_after_transfer(cfg, agreed_path=None):
    """After a send or pull: rebuild the engine dump and update the change feed now, so the page shows the new
    state at once and the feed records the transfer in this look rather than in a later one. With `agreed_path`
    (the file both sides now agree on) a metadata snapshot of that content is queued in the background, so a later
    conflict can show what each side changed since this point. The files are already written when this runs, so a
    failure here is returned as a message (the result's `refresh_error`), never raised: the caller must not report
    a transfer that happened as failed."""
    try:
        engines.dump(cfg, force=True)
        changes.update(cfg)
        if agreed_path:
            asset_meta.request_snapshot(cfg, agreed_path)
    except Exception as e:  # noqa: BLE001  (reported to the caller; the next scan retries)
        return f"{type(e).__name__}: {e}"
    return None
