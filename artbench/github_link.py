"""The GitHub account a project pushes as. Artbench never runs git or gh: it keeps the name in the project config,
reads which account the GitHub CLI is set to from gh's own hosts.yml, and hands out the switch command when they
differ."""
import os
import re

from . import config, store
from .errors import NotFound

GITHUB_USER = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")


def set_github_account(project_id, account):
    """Saves the GitHub account for one project ("" clears it); a history line records the change. NotFound for an
    unknown project, ValueError for a name GitHub would not accept. Returns github_status()."""
    account = (account or "").strip().lstrip("@")
    if account and not GITHUB_USER.match(account):
        raise ValueError(f"not a GitHub account name: {account!r}")
    cfg = next((c for c in config.projects() if c.get("id") == project_id and "error" not in c), None)
    if cfg is None:
        raise NotFound(f"project {project_id}")
    raw = store._read_json(cfg["config_path"], {})
    raw = raw if isinstance(raw, dict) else {}
    if account:
        raw["github_account"] = account
    else:
        raw.pop("github_account", None)
    store._write_json(cfg["config_path"], raw)
    store.log(cfg, "GITHUB", account or "-", "the account this project pushes as")
    return github_status(config.load(cfg["config_path"]))


def gh_config_dir():
    """Where the GitHub CLI keeps hosts.yml: GH_CONFIG_DIR, else %AppData%\\GitHub CLI on Windows, else the XDG
    config folder."""
    if os.environ.get("GH_CONFIG_DIR"):
        return os.environ["GH_CONFIG_DIR"]
    if os.name == "nt" and os.environ.get("APPDATA"):
        return os.path.join(os.environ["APPDATA"], "GitHub CLI")
    return os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config"), "gh")


def gh_active_user():
    """The account gh uses for github.com (the `user:` line of its github.com block), or None."""
    try:
        with open(os.path.join(gh_config_dir(), "hosts.yml"), encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return None
    inside, indent = False, None
    for line in lines:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line[0].isspace():
            inside, indent = line.strip() == "github.com:", None
            continue
        if inside:
            depth = len(line) - len(line.lstrip())
            indent = depth if indent is None else indent
            m = re.match(r"\s*user:\s*(\S+)\s*$", line)
            if m and depth == indent:
                return m.group(1).strip("\"'")
    return None


def repo_git_user(cfg):
    """"Name <email>" from the [user] section of the engine project's own .git/config, or None."""
    folder = cfg.get("engine_root")
    while folder:
        gitdir = os.path.join(folder, ".git")
        if os.path.isdir(gitdir):
            break
        parent = os.path.dirname(folder)
        folder = None if parent == folder else parent
    else:
        return None
    try:
        with open(os.path.join(gitdir, "config"), encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return None
    section, user = None, {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("["):
            section = line.strip("[]").strip().lower()
        elif section == "user" and "=" in line:
            key, value = (p.strip() for p in line.split("=", 1))
            user[key.lower()] = value
    if not user.get("name"):
        return None
    return f"{user['name']} <{user['email']}>" if user.get("email") else user["name"]


def github_status(cfg):
    """{"account", "active", "matches", "switch", "git_user"}: matches is None when either side is unknown; switch is
    the gh command to run when the project's account is not the active one."""
    account, active = cfg.get("github_account") or None, gh_active_user()
    matches = (account.lower() == active.lower()) if account and active else None
    switch = f"gh auth switch --hostname github.com --user {account}" if account and not matches else None
    return {"account": account, "active": active, "matches": matches, "switch": switch, "git_user": repo_git_user(cfg)}
