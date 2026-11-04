"""Typed errors the modules raise, so callers (the operations layer above all) decide by type, never by words in a
message that may contain asset, path or project names. Each subclasses the built-in it replaced, so existing
`except ValueError` / `except KeyError` code keeps working."""


class NotFound(KeyError):
    """A project, item, scene, task or graph node that does not exist."""

    def __str__(self):
        return str(self.args[0]) if self.args else ""


class NeedsForce(ValueError):
    """A transfer would overwrite work changed since the last sync (or with no sync record)."""


class WarningsNotAccepted(ValueError):
    """Fingerprint warnings exist and the caller did not accept them."""


class OutsideRoot(ValueError):
    """A source or target path lies outside the art root or the engine root."""


class Unavailable(ValueError):
    """What the operation needs is not there: no engine copy, no engine target."""


class Conflict(ValueError):
    """A destination is already taken."""


class WrongMode(ValueError):
    """The operation does not exist for the project's mode (an art-folder operation on a project-mode project)."""
