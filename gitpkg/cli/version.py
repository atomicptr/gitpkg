from gitpkg._version import __version__
from gitpkg.cli.console import console
from gitpkg.cli.root import root


@root.command("version", help="Print version info")
def cmd_version():
    console.print(__version__)
