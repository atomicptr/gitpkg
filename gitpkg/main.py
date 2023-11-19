import os

from gitpkg.cli import CLI


def main():
    cli = CLI(enable_debug_mode=os.getenv("GITPKG_DEBUG") is not None)
    cli.run()
