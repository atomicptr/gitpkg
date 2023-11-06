import argparse
import inspect
import logging
import os
import sys

from git import InvalidGitRepositoryError
from rich.logging import RichHandler

from gitpkg.console import console, fatal
from gitpkg.errors import GitPkgError
from gitpkg.package_manager import PackageManager

_COMMAND_PREFIX = "command_"


class CLI:
    _pm: PackageManager = None

    def run(self):
        if os.getenv("GITPKG_DEBUG") is not None:
            logging.basicConfig(
                level=logging.DEBUG,
                handlers=[RichHandler()],
            )

        try:
            self._pm = PackageManager.from_environment()
        except InvalidGitRepositoryError:
            fatal("could not find a git repository")

        parser = argparse.ArgumentParser(
            description="A git powered package manager built on top of "
                        "submodules.",
            usage=f"""git pkg <command> [<args>]

Commands:
{self._create_commands_list_str()}
        """)

        parser.add_argument("command", help="Subcommand to run")
        parser.add_help = False

        args = parser.parse_args(sys.argv[1:2])
        logging.debug(args)

        command_func = f"{_COMMAND_PREFIX}{args.command}"

        if not hasattr(self, command_func):
            parser.print_help()
            fatal(f"Unrecognized command: {args.command}")

        try:
            getattr(self, command_func)()
        except GitPkgError as err:
            fatal(err.raw_message)

    def _create_commands_list_str(self) -> str:
        commands: list[tuple[str, str]] = []

        for member in dir(self):
            if not member.startswith(_COMMAND_PREFIX):
                continue
            commands.append((
                member[len(_COMMAND_PREFIX):],
                getattr(self, member).__doc__,
            ))

        commands = sorted(commands, key=lambda cmd: cmd[0])

        command_names = [cmd[0] for cmd in commands]
        max_len = len(max(command_names, key=len))

        commands_list = ""

        for command, desc in commands:
            commands_list += f"\t{command.ljust(max_len)}\t{desc}\n"

        return commands_list

    def command_test(self):
        """Test command"""
        parser = argparse.ArgumentParser(
            description=inspect.stack()[0][3].__doc__,
        )

        parser.add_argument("--name")

        args = parser.parse_args(sys.argv[2:])
        logging.debug(args)
