"""The operations layer: every operation Artbench offers to programs (HTTP /api/v1, MCP, the command line) is one
entry here, with its argument schema and a typed error. The transports carry no logic of their own, so an operation
behaves the same whichever way it is called.

A package by subject: common (shared types and lookups), assets, work, transfer, machine (the
operations), registry (definitions and calls), page (what the page's own routes need)."""
from . import page  # noqa: F401  (the page's own routes; the server reaches them as ops.page)
from .assets import catalog_counts  # noqa: F401  (setup's summary)
from .common import ART_ONLY, BRIDGE_ONLY, CODES, GRAPH_CAP, LIST_CAP, WRITE_OPS, Op, OpError  # noqa: F401
from .registry import OPS, call, coerce, describe, to_error  # noqa: F401
