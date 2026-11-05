"""Marks on assets: a favourite star, a "revision coming" flag with its note, and tags (the person's own words), per project (marks.json in the
project's data folder, never in the game project). They are the person's own records, keyed by asset id (an
art-folder item id or engine:<path>); an asset with no mark left has no entry. Every change is a MARK history line."""
import os
import time

from . import store

MARKS_FILE = "marks.json"
TAG_MAX = 40


def _path(cfg):
    return os.path.join(store.data_dir(cfg), MARKS_FILE)


def load(cfg):
    """{asset id: {favorite?: true, revision?: {note, since}, tags?: [sorted], updated}}."""
    data = store._read_json(_path(cfg), {})
    return data if isinstance(data, dict) else {}


def tag_name(value):
    """A tag in its one form: lower case, single spaces; ValueError when empty or longer than TAG_MAX."""
    tag = " ".join(str(value).split()).lower()
    if not tag or len(tag) > TAG_MAX:
        raise ValueError(f"a tag is 1 to {TAG_MAX} characters: {value!r}")
    return tag


def set_marks(cfg, ids, favorite=None, revision=None, note=None, add_tags=None, remove_tags=None):
    """Sets marks on every id: favorite True or False; revision True or False (False clears its note); a note alone
    sets the revision flag with that note; add_tags / remove_tags change its tags. None leaves a mark as it is.
    Returns {id: entry, or None when cleared}."""
    ids = [i for i in (ids or []) if i]
    if not ids:
        raise ValueError("no asset ids given")
    add = {tag_name(t) for t in add_tags or []}
    remove = {tag_name(t) for t in remove_tags or []}
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
            if add or remove:
                tags = (set(entry.get("tags") or []) | add) - remove
                entry.pop("tags", None)
                if tags:
                    entry["tags"] = sorted(tags)
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
    if entry.get("tags"):
        parts.append("tags: " + ", ".join(entry["tags"]))
    return "; ".join(parts)


def tags(data):
    """{tag: assets carrying it}, the most used first, then by name."""
    per = {}
    for e in data.values():
        for tag in e.get("tags") or []:
            per[tag] = per.get(tag, 0) + 1
    return dict(sorted(per.items(), key=lambda kv: (-kv[1], kv[0])))


def counts(data):
    """Favourites and revisions; the tags with their counts only when any asset has one."""
    out = {"favorite": sum(1 for e in data.values() if e.get("favorite")),
           "revision": sum(1 for e in data.values() if e.get("revision"))}
    per = tags(data)
    if per:
        out["tags"] = per
    return out
