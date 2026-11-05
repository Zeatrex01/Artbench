"""Marks on assets: a favourite star and a "revision coming" flag with its note, per project (marks.json in the
project's data folder, never in the game project). They are the person's own records, keyed by asset id (an
art-folder item id or engine:<path>); an asset with no mark left has no entry. Every change is a MARK history line."""
import os
import time

from . import store

MARKS_FILE = "marks.json"


def _path(cfg):
    return os.path.join(store.data_dir(cfg), MARKS_FILE)


def load(cfg):
    """{asset id: {favorite?: true, revision?: {note, since}, updated}}."""
    data = store._read_json(_path(cfg), {})
    return data if isinstance(data, dict) else {}


def set_marks(cfg, ids, favorite=None, revision=None, note=None):
    """Sets marks on every id: favorite True or False; revision True or False (False clears its note); a note alone
    sets the revision flag with that note. None leaves a mark as it is. Returns {id: entry, or None when cleared}."""
    ids = [i for i in (ids or []) if i]
    if not ids:
        raise ValueError("no asset ids given")
    if revision is None and note is not None:
        revision = True
    now = time.time()
    out = {}
    with store.locked(cfg):
        data = load(cfg)
        for asset in ids:
            entry = {k: v for k, v in (data.get(asset) or {}).items() if k != "updated"}
            if favorite is True:
                entry["favorite"] = True
            elif favorite is False:
                entry.pop("favorite", None)
            if revision is True:
                before = entry.get("revision") or {}
                entry["revision"] = {"note": (note if note is not None else before.get("note", "")).strip(),
                                     "since": before.get("since", now)}
            elif revision is False:
                entry.pop("revision", None)
            if entry:
                entry["updated"] = now
                data[asset] = entry
            else:
                data.pop(asset, None)
            out[asset] = data.get(asset)
        store._write_json(_path(cfg), data)
        for asset in ids:
            store.log(cfg, "MARK", asset, describe(out[asset]))
    return out


def describe(entry):
    """One line for the history: what the asset carries now."""
    if not entry:
        return "no marks"
    parts = ["favorite"] if entry.get("favorite") else []
    if entry.get("revision"):
        parts.append("revision: " + (entry["revision"]["note"] or "(no note)"))
    return ", ".join(parts)


def counts(data):
    return {"favorite": sum(1 for e in data.values() if e.get("favorite")),
            "revision": sum(1 for e in data.values() if e.get("revision"))}
