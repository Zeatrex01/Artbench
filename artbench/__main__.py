"""python -m artbench: the command line (call, ops, setup, addon, shortcut) or, without a command, the page
server."""
import sys

if len(sys.argv) > 1 and sys.argv[1] in ("call", "ops", "setup", "addon", "shortcut"):    # the command line; else the page server
    from .cli import main as cli_main
    sys.exit(cli_main(sys.argv[1:]))

from .server import main

main()
